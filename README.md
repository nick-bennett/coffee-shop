# Coffee Shop

## Overview

This is a simple queueing system simulation, modeling a coffee shop. Customers arrive individually and independently, and then enter a single queue. One or more servers fill orders, and the customer leaves the shop when the order is completed.

## Input

All input parameters are read from YAML files, as follows:

### `config.yaml` properties

- `servers`: array of `server` objects, each with the following properties.

    - `name`: name used for server in logs
    - `service-time`: mean time for this server to process an order

- `customers`: single object, with the following property:

    - `interarrival-time`: mean time between arrivals

### `job.yaml` (optional)

- `random-seed`: optional seed value (default is no seed) for random number generator (for reproducible runs)

- `time`: single object (optional), with the following properties:

    - `limit`: optional maximum run length (default is 100) of the simulation, in simulated time
    - `reset`: optional reset time for aggregate statistics (default is 0), to support system warm-up; on reset, the RESET event is logged.

## Output

### Event log

#### Structure

This simulation does not prevent a graphical display, but instead logs all events (arrivals, service starts, service completions) in simulated time order. The log entries are comma-delimited, with the following columns; the column name (shown in quotes) is in a header row in the first line of the output:

- "Timestamp": simulated time of the event's occurrence.
- Event "Type": One of ARRIVAL, SERVICE_START, SERVICE_DONE, or RESET.
- "Customer" name: Identifier (based on automatically generated numeric ID of customer)—unless event is RESET, in which case this column is blank.
- "Server" name: Identifier if event is SERVICE_START or SERVICE_DONE, and blank otherwise.
- Queue "Length": Number of customers in queue after event processing.
- Servers "Available": Number of idle servers after event processing.

#### Order

As stated above, events in the log are in simulation time order. For events that happen at the same time (e.g., an arrival into an empty queue and the immediate start of service), the order shown in the log will be:

- RESET
- ARRIVAL
- SERVICE_DONE
- SERVICE_START

If multiple events of the same type occur at the same time, those events will be ordered by customer ID, then server name, both ascending.

#### Queue length and server availability measurement basis

The queue length logged for ARRIVAL and SERVICE_START events is the queue length resulting from the event. Similarly, the servers available logged for a SERVICE_START or SERVICE_DONE event is the number resulting from the event.

### Aggregate statistics

As the simulation proceeds, the system keeps track of the following aggregate statistics, presenting them (in the console) at the end of the simulation:

- Average queue length
- Maximum queue length
- Average time spent in the queue
- Queue length at the end of the simulation
- Average time spent in the queue by those customers still in the queue at the end of the simulation
- Number of customers for whom service was completed
- Average service time
- Number of customers being served at the end of the simulation
- Average service time for those customers being served at the end of the simulation
- Average server utilization by server
- Average server utilization overall

## Dependencies

- Python 3.13.x
- PyYAML 6.0.x
- SimPy 4.1.x
- NumPy 2.3.x
