from chat.chat_node import ChatNode
from constants.constants import DEFAULT_PORT

# Funzione che gestisce il flusso per connettersi come client a un server esistente.
# Richiede all’utente indirizzo e porta, tenta la connessione, gestisce eventuali errori e permette il retry.
def client_flow(username: str, default_port: int = DEFAULT_PORT):
    node = ChatNode(username) # Istanzia il nodo della chat con il nome utente fornit

    while True:
        # ottenimento dell'indirizzo del server e della porta
        host = input("Indirizzo server (default localhost): ").strip() or "localhost"

        try:
            port = int(input(f"Porta server (default {default_port}): ").strip() or default_port)
        except ValueError:
            port = default_port
            print(f"Porta non valida, uso {default_port}")

        print(f"Tentativo di connessione a {host}:{port}…")
        result = node.connect_as_client(host, port) # Tenta di connettersi al server

        # se il risultato è "success", ritorna il nodo e True
        if result == "success":
            return node, True

        # caso in cui il nome sia gia stato preso
        elif result == "username_taken":
            print("Nome utente già in uso!")
            if input("Vuoi riprovare con un altro nome utente? (s/N): ").strip().lower() != "s":
                node.shutdown()
                return node, False
            new_user = input("Nuovo nome utente: ").strip()
            while not new_user:
                new_user = input("Nome utente (obbligatorio): ").strip()
            node.shutdown()
            node = ChatNode(new_user)

        # caso in cui la connessione fallisca
        elif result == "connection_failed":
            print("Impossibile connettersi al server!")
            print("1. Riprova")
            print("2. Esci")

            while True:
                choice = input("Scelta (1/2): ").strip()
                if choice in ("1", "2"):
                    break
                print("Scelta non valida!")

            if choice == "1":
                continue
            else:
                node.shutdown()
                return node, False

        # in qualsiasi altro caso, stampa un errore generico
        else:
            print("Errore durante la connessione.")
            node.shutdown()
            return node, False
