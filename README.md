![Project](https://img.shields.io/badge/Project-Chat%20Peer--to--Peer-blue?style=flat)
![Course](https://img.shields.io/badge/University%20Project-Sistemi%20Distribuiti-lightgrey?style=flat)
![Academic Year](https://img.shields.io/badge/A.A.-2024%2F2025-informational?style=flat)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat&logo=python)
![Sockets](https://img.shields.io/badge/Networking-TCP%2FIP-green?style=flat)
![Threads](https://img.shields.io/badge/Concurrency-Threading-orange?style=flat)

# Peer-to-Peer Chat System

This repository contains the source code for a university project developed during the Bachelor’s Degree in Computer Science at the University of Urbino. The project was created for the course *Sistemi Distribuiti* (Distributed Systems) and focuses on implementing a fault-tolerant peer-to-peer chat system.
The system allows users to communicate through a decentralized network where each node can operate either as a client or as a server. If the main server disconnects, an election mechanism ensures that a new server is automatically promoted among the connected peers, maintaining the continuity of the chat service.

---

## What It Does

- **Peer-to-Peer Messaging**: Enables real-time message exchange among multiple connected nodes.
- **Automatic Server Promotion**: Promotes a new server automatically in case the current one becomes unavailable.
- **Socket Communication**: Uses TCP/IP sockets for direct communication between peers.
- **Multithreading**: Each node uses Python threads to handle multiple operations concurrently (sending, receiving, connecting).
- **Interactive CLI Interface**: The user interacts via a simple command-line interface to connect to the network and chat.
- **Graceful Shutdown**: Ensures clean termination of connections and election reset during node disconnection.

---

## How to run

Before running the project, make sure that each folder containing Python modules includes an `__init__.py` file.

### Why `__init__.py`?

The presence of `__init__.py` turns a directory into a Python package, allowing you to use **relative and absolute imports** across the project's modules. Without it, Python may not recognize the folders as part of the package structure, which can cause import errors.<br>
Even an empty `__init__.py` file is sufficient.

Once the project has been run successfully for the first time and Python has cached the module structure, you may remove the `__init__.py` files if they are no longer needed, especially if you're not using relative imports or packaging.

---

### Running the project

Once all `__init__.py` files are in place, you can launch the application from the root directory with:

```bash
python main.py
```

---
## How It Works

Once the project is started with `python main.py`, the application launches in the terminal and guides the user through a series of steps:

1. **Username Selection**  
   The first prompt asks the user to input a **unique** username that will be used to identify them in the chat. This name is visible to all other connected peers.

2. **Mode Selection**  
   The user is then asked whether they want to:
   - start as a **server**, or
   - connect to an existing server as a **client**.

3. **Server Mode**  
   If acting as a server, the node starts listening for incoming client connections. A message is displayed to confirm that the server is running and ready.

4. **Client Mode**  
   If acting as a client, the user is asked to enter the IP address (or hostname) and port number of the server they wish to connect to.  
   The application attempts the connection and retries if it fails.

5. **Chat Initialization**  
   Once connected (either as server or client), the chat becomes active. Users can start sending messages.  
   All messages are broadcast to every connected peer in real time.

6. **Automatic Server Promotion**  
   If the server disconnects, the system automatically starts an election among the clients.  
   One of the clients is promoted to server, ensuring the chat continues without interruption.

7. **Clean Exit**  
   To leave the chat gracefully, users can type the command `quit` in the terminal. This will trigger a proper shutdown sequence, closing sockets and threads cleanly.  
   Alternatively, pressing `CTRL+C` also exits the program, but it may skip certain cleanup operations.

This flow ensures a robust and resilient peer-to-peer communication experience directly from the terminal, without the need for a central server.

## Contributors

![avatar](https://images.weserv.nl/?url=github.com/KevAtta.png?v=4&h=80&w=80&fit=cover&mask=circle&maxage=7d)
![avatar](https://images.weserv.nl/?url=https://github.com/GioRoss.png?v=4&h=80&w=80&fit=cover&mask=circle&maxage=7d)
