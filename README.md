# Coffee Shop

## Overview

This is a simple queueing system simulation, modeling a coffee shop. Customers arrive individually and independently, and then enter a single queue. One or more servers fill orders, and the customer leaves the shop when the order is completed.

## Input

All input parameters are read from YAML files.

## Output

This simulation does not prevent a graphical display, but instead logs all events (arrivals, service starts, service completions) in simulated time order. As the simulation proceeds, the system keeps track of aggregate statistics, displaying these at the end of the simulation:

- Average queue length
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
