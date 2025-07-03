from main.modes.server_mode import server_flow
from main.modes.client_mode import client_flow
from main.banner import print_banner
from constants.constants import DEFAULT_PORT, DEFAULT_HOST

# Funzione principale che gestisce l'avvio dell'applicazione
def main() -> None:
    print_banner() # Mostra il banner iniziale

    username = input("Il tuo nome utente: ").strip()
    while not username:
        username = input("Nome utente (obbligatorio): ").strip()

    print("\nCome vuoi partecipare?")
    print("1. Avvia una nuova chat (diventerai il server)")
    print("2. Unisciti a una chat esistente (diventerai client)")

    # ciclo per assicurarsi che l'utente scelga un'opzione valida
    while True:
        choice = input("Scelta (1/2): ").strip()
        if choice in ("1", "2"):
            break
        print("Scelta non valida!")

    # Avvia il flusso server o client in base alla scelta   
    if choice == "1":
        node, ok = server_flow(username, host=DEFAULT_HOST, default_port=DEFAULT_PORT)
    else:
        node, ok = client_flow(username, default_port=DEFAULT_PORT)

    if not ok:
        print("Impossibile avviare / connettersi alla chat.")
        return

    # mostra comandi a seconda del tipo di nodo
    print("\nComandi disponibili:")
    if node.is_server:
        print("  list    - Mostra client connessi")
        print("  quit    - Chiudi server")
    else:
        print("  quit    - Disconnetti")
    print("  <testo> - Invia messaggio a tutti")

    # ciclo di input di inserimento messaggi
    try:
        while node.running:
            text = input().strip()
            if not text:
                continue
            if text.lower() in {"quit", "exit", "q"}:
                break
            if text.lower() == "list" and node.is_server:
                node.list_connected_users()
            else:
                node.send_message(text)
    except KeyboardInterrupt:
        print("\nInterruzione ricevuta…")
    finally:
        node.shutdown()

# Avvia l'applicazione
if __name__ == "__main__":
    main()