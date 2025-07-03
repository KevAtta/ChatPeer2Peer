from chat.chat_node import ChatNode
from constants.constants import DEFAULT_HOST, DEFAULT_PORT

# Funzione che gestisce il flusso per avviare un server di chat.
# Chiede la porta, avvia il server e restituisce (node, success).
def server_flow(username: str, host: str = DEFAULT_HOST, default_port: int = DEFAULT_PORT):
    node = ChatNode(username)

    while True:
        try:
            port = int(input(f"Porta di ascolto (default {default_port}): ").strip() or default_port)
        except ValueError:
            port = default_port
            print(f"Porta non valida, uso {default_port}")

        if node.start_as_server(host, port): # avvia il nodo come server
            return node, True

        # caso in cui il bind fallisce, allora richiedi all’utente se ritentare
        retry = input("Porta occupata o errore. Vuoi riprovare? (s/N): ").strip().lower()
        if retry != "s":
            node.shutdown()
            return node, False
