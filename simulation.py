#!/usr/bin/env python3
"""
Coffee Shop queueing simulation

Implements the simulation and output logic described in README.md using
- deterministic interarrival times (from config.yaml -> customers.interarrival-time)
- deterministic, per-server service times (from config.yaml -> servers[].service-time)
- optional job.yaml for time-limit (default 100) and random-seed (not used for deterministic logic)

Outputs:
- CSV event log to stdout with columns:
  Timestamp, Event type, Customer, Server, Length, Available
- Followed by aggregate statistics printed in human-readable text.

This implementation uses SimPy to advance simulated time while controlling
assignments through a simple FIFO queue and explicit server processes to
preserve server names in logs.
"""
from __future__ import annotations

import os
import sys
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import simpy
import yaml


# ---------- Data models ----------

@dataclass
class Customer:
    cid: int
    arrival_time: float
    # will be set when service starts
    service_start_time: Optional[float] = None
    server_name: Optional[str] = None
    # constant service time chosen when assigned (depends on server)
    service_time: Optional[float] = None


@dataclass
class Server:
    name: str
    service_time: float
    busy: bool = False
    # For utilization tracking
    busy_time_accum: float = 0.0
    last_state_change: float = 0.0  # last time busy flag changed
    # Currently served customer id (if any)
    current_cid: Optional[int] = None

    def set_busy(self, env_now: float, busy: bool) -> None:
        # Update accumulated busy time up to now, then change state
        if self.busy:
            self.busy_time_accum += env_now - self.last_state_change
        self.busy = busy
        self.last_state_change = env_now


# ---------- Simulation ----------

class CoffeeShopSim:
    def __init__(self, env: simpy.Environment, servers: List[Server], interarrival_time: float, time_limit: float):
        self.env = env
        self.servers = servers
        self.N = len(servers)
        self.interarrival_time = float(interarrival_time)
        self.time_limit = float(time_limit)

        # Queue of waiting customers (FIFO)
        self.queue: Deque[Customer] = deque()

        # Stats
        self.next_cid = 1
        self.area_under_q: float = 0.0
        self.last_q_change_time: float = 0.0
        self.cur_q_len: int = 0
        self.max_q_len: int = 0

        self.total_wait_time: float = 0.0
        self.count_started: int = 0  # customers who started service
        self.total_service_time_completed: float = 0.0
        self.count_completed: int = 0

        # Track customers still in queue at end
        self.waiting_customers: Dict[int, Customer] = {}
        # Track in-service customers at any time
        self.in_service: Dict[int, Customer] = {}

        # Output: print CSV header immediately
        print("Timestamp,Event type,Customer,Server,Length,Available")

    # ----- Logging helpers -----
    def _update_q_time_area(self, now: float) -> None:
        dt = now - self.last_q_change_time
        if dt > 0:
            self.area_under_q += self.cur_q_len * dt
            self.last_q_change_time = now

    def _set_q_len(self, now: float, new_len: int) -> None:
        self._update_q_time_area(now)
        self.cur_q_len = new_len
        if self.cur_q_len > self.max_q_len:
            self.max_q_len = self.cur_q_len

    def servers_available(self) -> int:
        return sum(0 if s.busy else 1 for s in self.servers)

    def log(self, now: float, event_type: str, customer: Optional[Customer], server_name: str = "") -> None:
        cust_name = f"C{customer.cid}" if customer else ""
        # Queue length and servers available should reflect state AFTER event is processed
        print(f"{now:.6g},{event_type},{cust_name},{server_name},{self.cur_q_len},{self.servers_available()}")

    # ----- Processes -----
    def arrivals_process(self):
        while True:
            # Next arrival time
            if self.env.now > self.time_limit:
                break
            # Create and process arrival at current time
            c = Customer(cid=self.next_cid, arrival_time=self.env.now)
            self.next_cid += 1

            # Arrival event changes queue length (+1)
            self.queue.append(c)
            self.waiting_customers[c.cid] = c
            self._set_q_len(self.env.now, len(self.queue))
            # ARRIVAL log (servers availability unchanged by arrival itself)
            self.log(self.env.now, "ARRIVAL", c)

            # Immediately try to dispatch after arrival
            self.try_dispatch()

            # Schedule next arrival
            next_time = self.env.now + self.interarrival_time
            if next_time > self.time_limit:
                # Move to time_limit to allow servers to continue processing, then stop arrivals
                yield self.env.timeout(self.time_limit - self.env.now)
                break
            else:
                yield self.env.timeout(self.interarrival_time)

    def try_dispatch(self):
        # While there is at least one free server and a waiting customer, start service
        while self.queue and any(not s.busy for s in self.servers):
            # Pick the first free server by order
            server = next(s for s in self.servers if not s.busy)
            customer = self.queue.popleft()
            self.waiting_customers.pop(customer.cid, None)

            # SERVICE_START effects: queue length -1, server becomes busy
            self._set_q_len(self.env.now, len(self.queue))

            # Assign attributes
            customer.service_start_time = self.env.now
            customer.server_name = server.name
            customer.service_time = server.service_time

            # Update stats for waiting time
            wait_time = customer.service_start_time - customer.arrival_time
            self.total_wait_time += wait_time
            self.count_started += 1

            # Mark server busy (utilization tracking)
            server.current_cid = customer.cid
            server.set_busy(self.env.now, True)

            # Log SERVICE_START (after state changed)
            self.log(self.env.now, "SERVICE_START", customer, server.name)

            # Add to in-service tracking
            self.in_service[customer.cid] = customer

            # Start the service process
            self.env.process(self.service_process(customer, server))

    def service_process(self, customer: Customer, server: Server):
        # Deterministic service time per server
        service_time = float(server.service_time)
        # Advance time
        yield self.env.timeout(service_time)

        # Service done: update stats, free server
        self.total_service_time_completed += service_time
        self.count_completed += 1

        # Mark server free (update utilization accum through set_busy)
        server.set_busy(self.env.now, False)
        server.current_cid = None

        # Remove from in-service
        self.in_service.pop(customer.cid, None)

        # Log SERVICE_DONE (queue length unchanged)
        self.log(self.env.now, "SERVICE_DONE", customer, customer.server_name or server.name)

        # After completing service, immediately try to dispatch next customer if available
        self.try_dispatch()

    # ----- Run and finalization -----
    def run(self):
        # Start arrivals
        self.env.process(self.arrivals_process())
        # Run until time limit
        self.env.run(until=self.time_limit)

    def finalize_and_print_stats(self):
        # Close out queue time area up to end time
        end_time = self.env.now
        self._update_q_time_area(end_time)

        total_time = max(end_time, 0.0)
        avg_q_len = (self.area_under_q / total_time) if total_time > 0 else 0.0
        max_q_len = self.max_q_len

        # Queue stats
        queue_len_end = self.cur_q_len
        if self.waiting_customers:
            avg_wait_remaining = sum(end_time - c.arrival_time for c in self.waiting_customers.values()) / len(self.waiting_customers)
        else:
            avg_wait_remaining = 0.0

        # Service stats
        avg_wait_time = (self.total_wait_time / self.count_started) if self.count_started > 0 else 0.0
        avg_service_time_completed = (self.total_service_time_completed / self.count_completed) if self.count_completed > 0 else 0.0
        num_in_service_end = sum(1 for s in self.servers if s.busy)
        if self.in_service:
            avg_service_time_in_service = sum(c.service_time or 0.0 for c in self.in_service.values()) / len(self.in_service)
        else:
            avg_service_time_in_service = 0.0

        # Server utilization (per-server and overall)
        per_server_util: List[Tuple[str, float]] = []
        busy_sum = 0.0
        for s in self.servers:
            # If still busy at end, account time till end
            if s.busy:
                s.busy_time_accum += end_time - s.last_state_change
                s.last_state_change = end_time
            util = (s.busy_time_accum / total_time) if total_time > 0 else 0.0
            per_server_util.append((s.name, util))
            busy_sum += s.busy_time_accum
        overall_util = (busy_sum / (self.N * total_time)) if self.N > 0 and total_time > 0 else 0.0

        # Print aggregates (human-readable)
        print()
        print("Aggregate statistics:")
        print(f"- Average queue length: {avg_q_len:.6g}")
        print(f"- Maximum queue length: {max_q_len}")
        print(f"- Average time spent in the queue: {avg_wait_time:.6g}")
        print(f"- Queue length at the end of the simulation: {queue_len_end}")
        print(f"- Average time spent in the queue by those customers still in the queue at the end of the simulation: {avg_wait_remaining:.6g}")
        print(f"- Number of customers for whom service was completed: {self.count_completed}")
        print(f"- Average service time: {avg_service_time_completed:.6g}")
        print(f"- Number of customers being served at the end of the simulation: {num_in_service_end}")
        print(f"- Average service time for those customers being served at the end of the simulation: {avg_service_time_in_service:.6g}")
        # Per-server utilization
        for name, util in per_server_util:
            print(f"- Average server utilization for {name}: {util:.6g}")
        print(f"- Average server utilization overall: {overall_util:.6g}")


# ---------- YAML loading ----------

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_inputs(config_path: str = "config.yaml", job_path: str = "job.yaml") -> Tuple[List[Server], float, float, Optional[int]]:
    if not os.path.exists(config_path):
        print(f"ERROR: Missing required config file: {config_path}", file=sys.stderr)
        sys.exit(1)
    config = load_yaml(config_path)

    # Schema per README.md
    servers_data = config.get("servers")
    if not isinstance(servers_data, list) or not servers_data:
        print("ERROR: config.yaml must contain a non-empty 'servers' array.", file=sys.stderr)
        sys.exit(1)

    servers: List[Server] = []
    for entry in servers_data:
        if not isinstance(entry, dict):
            print("ERROR: Each server entry must be a mapping with 'name' and 'service-time'.", file=sys.stderr)
            sys.exit(1)
        name = entry.get("name")
        st = entry.get("service-time")
        if name is None or st is None:
            print("ERROR: Each server must have 'name' and 'service-time'.", file=sys.stderr)
            sys.exit(1)
        try:
            st_val = float(st)
        except Exception:
            print(f"ERROR: service-time for server '{name}' must be numeric.", file=sys.stderr)
            sys.exit(1)
        servers.append(Server(name=str(name), service_time=st_val))

    customers = config.get("customers", {})
    if not isinstance(customers, dict) or "interarrival-time" not in customers:
        print("ERROR: config.yaml must contain 'customers.interarrival-time'.", file=sys.stderr)
        sys.exit(1)

    try:
        interarrival_time = float(customers["interarrival-time"])    
    except Exception:
        print("ERROR: customers.interarrival-time must be numeric.", file=sys.stderr)
        sys.exit(1)

    job: dict = {}
    if os.path.exists(job_path):
        job = load_yaml(job_path)

    time_limit = float(job.get("time-limit", 100))
    seed = job.get("random-seed")
    try:
        seed_val: Optional[int] = int(seed) if seed is not None else None
    except Exception:
        seed_val = None

    return servers, interarrival_time, time_limit, seed_val


# ---------- Entry point ----------

def main(argv: List[str]) -> int:
    # Allow optional paths via args
    config_path = "config.yaml"
    job_path = "job.yaml"
    if len(argv) >= 2:
        config_path = argv[1]
    if len(argv) >= 3:
        job_path = argv[2]

    servers, interarrival_time, time_limit, seed = parse_inputs(config_path, job_path)

    # Deterministic model doesn't use RNG, but honor seed for completeness if needed later
    if seed is not None:
        try:
            import random
            random.seed(seed)
        except Exception:
            pass

    env = simpy.Environment()
    sim = CoffeeShopSim(env, servers, interarrival_time, time_limit)
    sim.run()
    sim.finalize_and_print_stats()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
