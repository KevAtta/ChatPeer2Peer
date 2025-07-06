import socket
import threading
import json
import time
import signal
import sys
import os
from datetime import datetime
from utils.helpers import get_timestamp
from constants.constants import BUFFER_SIZE
from constants.constants import DEFAULT_PORT
from constants.constants import DEFAULT_HOST
from termcolor import colored   # da installare con "pip install termcolor"
import colorama                 # da installare con "pip install colorama"
colorama.init(autoreset=True)   # Inizializza colorama

class ChatNode:
    # Costruttore della classe ChatNode.
    # Inizializza le variabili di stato per distinguere tra client e server, gestire connessioni, thread, segnali e promozione.
    def __init__(self, username, max_connections = 5):
        self.username = username
        self.max_connections = max_connections
        
        # modalità dell'utente
        self.is_server = False
        self.is_client = False
        
        # dati per modalità server
        self.server_socket = None
        self.connected_clients = {} # dizionario con i client connessi: {socket: info}
        self.server_running = False # stato del ciclo di accettazione client
        
        # dati per modalità client  
        self.client_socket = None
        self.connected_to_server = False
        self.server_username = ""
        self.server_host = ""
        self.server_port = 0
        self.peer_list = []
        self.connection_time = 0
        
        self.running = True
        self.promotion_in_progress = False
        self.promotion_lock = threading.Lock()  # lock per sincronizzazione promozione
        self.shutdown_event = threading.Event() # evento che segnala ai thread quando il nodo va in shutdown
        
        # thread tracking per cleanup
        self.active_threads = []
        self.thread_lock = threading.Lock()
        
        # gestione elezione leader deterministica
        self.election_in_progress = False
        self.election_lock = threading.Lock()
        self.my_election_id = None
        self.election_start_time = None
        
        # setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler) # gestione del segnale Ctrl+C (SIGINT)
        signal.signal(signal.SIGTERM, self.signal_handler) # estione della terminazione da sistema (SIGTERM)
        
        # Sistema di logging
        self.chat_log = []  # lista per memorizzare i messaggi
        self.log_directory = "chat_logs"  # directory per i file di log
        self.ensure_log_directory()
    
    # Funzione che crea la directory per i log se non esiste già
    def ensure_log_directory(self):
        # controlla se la directory specificata in self.log_directory esiste, nel caso non esiste la crea
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)
    
    # Aggiunge un nuovo messaggio alla struttura interna di log
    def add_to_log(self, message_type, username, message, timestamp=None):
        # se non viene fornito un timestamp, genera uno nuovo
        if timestamp is None:
            timestamp = get_timestamp()
        
        # creazione un dizionario con tutti i metadati del messaggio
        log_entry = {
            'timestamp': timestamp,
            'type': message_type,
            'username': username,
            'message': message
        }
        
        # aggiunge l'entry alla lista interna dei log
        self.chat_log.append(log_entry)
    
    # Salva il log completo della chat in un file di testo. Il file viene creato nella directory di log con un nome univoco basato su
    # username e intervallo temporale della sessione
    def save_chat_log(self):
        # controlla se ci sono messaggi da salvare
        if not self.chat_log:
            print("Nessun messaggio da salvare nel log.")
            return
        
        # Genera nome file con timestamp
        now = datetime.now() # ottiene il timestamp corrente
        session_start = datetime.fromtimestamp(self.connection_time if hasattr(self, 'connection_time') else time.time()) # determina l'inizio della sessione: usa connection_time se disponibile, altrimenti il momento attuale
        
        # costruisce il nome del file con pattern: chat_log_username_start_to_end.log
        filename = f"chat_log_{self.username}_{session_start.strftime('%Y%m%d_%H%M%S')}_to_{now.strftime('%Y%m%d_%H%M%S')}.log"
        # crea il percorso completo combinando directory e nome file
        filepath = os.path.join(self.log_directory, filename)
        
        try:
            # apre il file in modalità scrittura con codifica UTF-8
            with open(filepath, 'w', encoding='utf-8') as f:
                # intestazione del log
                f.write("="*80 + "\n")
                f.write(f"CHAT LOG - Utente: {self.username}\n")
                f.write(f"Sessione: {session_start.strftime('%Y-%m-%d %H:%M:%S')} - {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Modalità: {'SERVER' if self.is_server else 'CLIENT'}\n")

                # se è un client, aggiunge le informazioni del server di connessione
                if self.is_client:
                    f.write(f"Server: {self.server_username} ({self.server_host}:{self.server_port})\n")
                f.write("="*80 + "\n\n")
                
                # itera attraverso tutti i messaggi nel log
                for entry in self.chat_log:
                    # estrae i campi dal dizionario dell'entry
                    timestamp = entry['timestamp']
                    msg_type = entry['type']
                    username = entry['username']
                    message = entry['message']
                    
                    # formatta il messaggio in base al tipo
                    if msg_type == 'chat_message':
                        f.write(f"[{timestamp}] {username}: {message}\n")  # messaggio di un client
                    elif msg_type == 'server_message':
                        f.write(f"[{timestamp}] {username} (SERVER): {message}\n") # messaggio del server con identificazione specifica
                    elif msg_type == 'system':
                        f.write(f"[{timestamp}] >>> {message}\n") # messaggio di sistema (connessioni, disconnessioni, etc.)
                
                # footer del log
                f.write("\n" + "="*80 + "\n")
                f.write("FINE LOG\n")
            
            print(f"Chat salvata in: {filepath}")

        # cattura eventuali errori durante la scrittura    
        except Exception as e:
            print(f"Errore nel salvare il log: {e}")

    # Funzione che gestisce i segnali di terminazione del processo (es. Ctrl+C).
    # Avvia lo shutdown ordinato del nodo e termina il programma.
    def signal_handler(self, signum, frame):
        print("\nSegnale di terminazione ricevuto...")
        self.shutdown()
        sys.exit(0)

    # Funzione che registra un nuovo thread nell'elenco dei thread attivi.
    # Imposta il thread come daemon per permettere l'uscita dal programma anche se è ancora in esecuzione.
    def add_thread(self, thread):
        thread.daemon = True
        with self.thread_lock:
            self.active_threads.append(thread)

    # Funzione che attende la terminazione dei thread attivi in modo ordinato.
    # I thread vengono joinati con timeout, ma essendo daemon non bloccano comunque l'uscita dal programma.
    def cleanup_threads(self):
        with self.thread_lock: # acquisisce il lock per operare sulla lista dei thread in sicurezza
            self.shutdown_event.set() # segnala ai thread attivi che è in corso lo shutdown
            for thread in self.active_threads[:]: # crea una copia della lista per iterare
                if thread.is_alive(): # controlla se il thread è ancora attivo
                    thread.join(timeout=3.0) # attende al massimo 3 secondi la sua terminazione
            self.active_threads.clear() # pulisce la lista dei thread dopo lo shutdown

    # Funzione che avvia il nodo in modalità server.
    # Crea il socket server, lo configura, lo mette in ascolto e avvia il thread per accettare connessioni dai client.
    # Restituisce True se il server viene avviato correttamente, False in caso di errore.
    def start_as_server(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # crea il socket TCP per il server
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # permette il riutilizzo dell'indirizzo
            self.server_socket.settimeout(1.0) # imposta un timeout per l'accept non bloccante
            self.server_socket.bind((host, port)) # collega il socket all'host e porta specificati
            self.server_socket.listen(self.max_connections) # inizia ad ascoltare le connessioni in ingresso

            self.is_server = True
            self.is_client = False
            self.server_running = True
            self.server_host = host
            self.server_port = port

            print("SERVER AVVIATO")
            print(f"Server '{self.username}' in ascolto su {host}:{port}")
            print(f"Massimo {self.max_connections} client consentiti")
            print("=" * 60)
            print("In attesa che altri utenti si connettano...")
            print("Digita i tuoi messaggi per inviarli a tutti i client")
            print("=" * 60)

            accept_thread = threading.Thread(target=self.accept_clients, name="AcceptThread") # crea un thread per accettare client
            self.add_thread(accept_thread) # registra il thread nella lista gestita
            accept_thread.start() # avvia il thread per la gestione delle connessioni in entrata

            return True

        except Exception as e:
            print(f"Errore nell'avvio del server: {e}")
            self.is_server = False
            self.server_running = False
            return False
    
    # Funzione che tenta di connettersi al server come client.
    # Esegue l’handshake iniziale con username e timestamp, e avvia un thread per ricevere messaggi.
    # Restituisce uno stato che descrive l’esito della connessione, gli stati possibili sono:
    # "success" - Connessione riuscita
    # "username_taken" - Nome utente già in uso
    # "connection_failed" - Impossibile connettersi (server non disponibile/porta sbagliata)
    # "error" - Altri errori
    def connect_as_client(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # Crea socket TCP
            self.client_socket.settimeout(10.0)  # Imposta timeout per la connessione
            
            try:
                self.client_socket.connect((host, port)) # Tenta la connessione al server
            except (socket.error, ConnectionRefusedError, OSError) as e: # nel caso di fossero errori di connessione come server non disponibile, porta chiusa, etc. 
                self.client_socket.close()
                return "connection_failed"
            
            # Disattiva timeout dopo la connessione
            self.client_socket.settimeout(None)
            
            self.server_host = host
            self.server_port = port
            self.connection_time = time.time() # registra il tempo di connessione
            
            # creazione del messaggio di handshake
            # include il tipo di richiesta, il nome utente e il tempo di connessione
            handshake = {
                'type': 'join_request',
                'username': self.username,
                'connection_time': self.connection_time
            }
            
            try:
                self.client_socket.send(json.dumps(handshake).encode('utf-8')) # Invio del messaggio di handshake al server
                response_data = self.client_socket.recv(BUFFER_SIZE).decode('utf-8') # Ricezione della risposta dal server
                response = json.loads(response_data) # Decodifica della risposta JSON
            except (socket.error, json.JSONDecodeError) as e: # caso di errore durante l'handshake
                self.client_socket.close()
                return "connection_failed"
            
            # se la risposta è di tipo 'join_accepted', allora la connessione è riuscita
            if response['type'] == 'join_accepted':
                self.is_client = True
                self.connected_to_server = True
                self.server_username = response['server_username']
                self.peer_list = response.get('peer_list', [])
                
                print("CONNESSO AL SERVER")
                print(f"Connesso al server '{self.server_username}' su {host}:{port}")
                print("=" * 60)
                print("Digita i tuoi messaggi per inviarli a tutti nella chat")
                print("Digita 'quit' per disconnetterti")
                print("=" * 60)
                
                receive_thread = threading.Thread(target=self.receive_from_server, name="ReceiveThread") # Thread per ricevere messaggi dal server
                self.add_thread(receive_thread) # Registra il thread nella lista gestita dal nodo
                receive_thread.start() # Avvia il thread di ricezione
                
                return "success"
            
            # se la risposta è di tipo 'join_rejected' (esempio server pieno), allora la connessione è stata rifiutata
            elif response['type'] == 'join_rejected':
                print(f"Connessione rifiutata: {response['message']}")
                self.client_socket.close() # Chiude il socket
                return "connection_failed" 
            
            # se la risposta è di tipo 'error', allora c'è stato un errore
            elif response['type'] == 'error':
                error_message = response['message']
                self.client_socket.close() # Chiude il socket
                
                # Distingui tra nome utente già in uso e altri errori
                if "nome utente" in error_message.lower() or "username" in error_message.lower():
                    return "username_taken"
                else:
                    return "error"

        # caso di altri tipi di errore (DNS, timeout generale, etc.)
        except Exception as e:
            print(f"Errore durante la connessione: {e}")
            if self.client_socket:
                try:
                    self.client_socket.close()
                except:
                    pass
            
            # classifica il tipo di errore per fornire un messaggio più specifico
            if isinstance(e, socket.gaierror):
                # errore DNS - hostname non valido
                return "connection_failed"
            elif isinstance(e, (ConnectionRefusedError, socket.timeout)):
                # connessione rifiutata o timeout
                return "connection_failed"
            else:
                return "error"

    # Funzione che gestisce l'accettazione e la registrazione di un nuovo client.
    # Esegue l'handshake, controlla se l'username è disponibile, aggiorna lo stato del server e avvia il thread di gestione messaggi.
    def handle_new_client(self, client_socket, client_address):
        try:
            client_socket.settimeout(10.0)  # timeout per la ricezione dell'handshake
            join_data = client_socket.recv(BUFFER_SIZE).decode('utf-8') # riceve i dati di join dal client
            join_request = json.loads(join_data) # decodifica i dati JSON ricevuti
            client_socket.settimeout(None)  # rimuovi timeout dopo handshake
            
            # verifica che il messaggio sia effettivamente una richiesta di join altrimenti chiude la connessione
            if join_request['type'] != 'join_request':
                client_socket.close()
                return
            
            client_username = join_request['username']
            client_connection_time = join_request.get('connection_time', time.time())
            
            # verifica se l'username è già in uso
            if self.is_username_taken(client_username):
                self.send_to_client(client_socket, { # invia un messaggio di errore al client e chiudo la connessione
                    'type': 'error',
                    'message': 'Nome utente già in uso'
                })
                client_socket.close()
                return
            
            # registra il nuovo client nella lista dei connessi
            self.connected_clients[client_socket] = {
                'username': client_username,
                'address': client_address,
                'connection_time': client_connection_time
            }
            
            print(f">>> {client_username} si è connesso ({client_address[0]}:{client_address[1]})")
            self.show_client_count() # mostra il numero aggiornato di client connessi
            
            peer_list = self.get_peer_list_for_client() # recupera la lista dei peer da inviare al nuovo client
            
            # invia conferma di connessione al client
            self.send_to_client(client_socket, {
                'type': 'join_accepted',
                'server_username': self.username,
                'message': f'Client connessi: {len(self.connected_clients)}/{self.max_connections}',
                'peer_list': peer_list
            })
            
            # informa gli altri client della nuova connessione
            self.broadcast_to_clients({
                'type': 'user_joined',
                'username': client_username,
                'message': f'{client_username} si è unito alla chat',
                'peer_list': peer_list
            }, exclude_socket=client_socket)
            
            # crea un thread per gestire i messaggi del nuovo client
            client_thread = threading.Thread(
                target=self.handle_client_messages, 
                args=(client_socket,),
                name=f"Client-{client_username}"
            )
            self.add_thread(client_thread) # registra il thread nella lista attiva
            client_thread.start() # vvvia il thread

        except Exception as e:
            print(f"Errore nella gestione del nuovo client: {e}")
            if client_socket in self.connected_clients: # controlla se il client è stato registrato nella lista dei connessi
                del self.connected_clients[client_socket] # rimozione del riferimento del client per evitare memory leak o errori futuri
            try:
                client_socket.close() # tenta di chiudere il socket per liberare risorse
            except:
                pass

    # Funzione che costruisce e restituisce la lista dei peer attualmente connessi,
    # ordinati per tempo di connessione. Include il server come primo elemento.
    def get_peer_list_for_client(self):
        peer_list = []
        
        # aggiunge il server come primo peer nella lista
        peer_list.append({
            'username': self.username,
            'is_server': True,
            'connection_time': 0,
            'host': self.server_host,
            'port': self.server_port
        })
        
        # ordina i client per tempo di connessione crescente
        clients_sorted = sorted(
            self.connected_clients.items(),
            key=lambda x: x[1]['connection_time']
        )
        
        # per ogni client connesso aggiunge le informazioni nella lista dei peer
        for socket, info in clients_sorted:
            peer_list.append({
                'username': info['username'],
                'is_server': False,
                'connection_time': info['connection_time'],
                'address': info['address']
            })
        
        return peer_list

    # Funzione eseguita in un thread dedicato per ricevere messaggi dal server.
    # Resta in ascolto finché il client è connesso e il sistema non è in shutdown.
    def receive_from_server(self):
        try:
            # cicla finché la connessione è attiva
            while self.connected_to_server and self.running and not self.shutdown_event.is_set():
                try:
                    self.client_socket.settimeout(1.0) # imposta un timeout di 1 secondo per il socket
                    data = self.client_socket.recv(BUFFER_SIZE).decode('utf-8') # riceve e decodifica i dati
                    self.client_socket.settimeout(None) # rimuove il timeout dopo la ricezione
                    
                    # se non arriva nulla, il server si è probabilmente disconnesso
                    if not data:
                        print("\nServer disconnesso!")
                        break
                    
                    message_data = json.loads(data) # converte il messaggio ricevuto in un dizionario
                    self.process_server_message(message_data) # elabora il messaggio ricevuto dal server
                    
                except socket.timeout:
                    continue  # Continua il loop
                except socket.error: # errore di connessione: presumibilmente il server è stato chiuso
                    print("\nConnessione al server persa!")
                    break 
                except Exception as e:
                    print(f"Errore nella ricezione: {e}")
                    break
        
        except Exception as e:
            if self.connected_to_server and not self.shutdown_event.is_set(): # mostra errori solo se il client è ancora attivo
                print(f"Errore fatale nella ricezione: {e}")
        finally:
            # se lo shutdown non è già in corso gestisce la disconessione del server
            if not self.shutdown_event.is_set():
                self.handle_server_disconnect()

    # Funzione che gestisce i messaggi ricevuti dal server.
    # Analizza il tipo di messaggio e agisce di conseguenza: stampa messaggi, aggiorna peer o rileva disconnessione.
    def process_server_message(self, message_data):
        # messaggio di chat da un altro utente quindi stampa il messaggio con timestamp e nome utente
        if message_data['type'] == 'chat_message':
            timestamp = message_data.get('timestamp', get_timestamp())
            username = message_data['username']
            message = message_data['message']
            
            # aggiunta messaggio alla struttura di log (per i client)
            self.add_to_log('chat_message', username, message, timestamp)
            
            print(f"[{timestamp}] {colored(username, 'yellow')} ha scritto: {message}")
        
        # messaggio del server
        elif message_data['type'] == 'server_message':
            timestamp = message_data.get('timestamp', get_timestamp())
            message = message_data['message']
            
            # aggiunta messaggio alla struttura di log (per i server)
            self.add_to_log('server_message', self.server_username, message, timestamp)
            
            print(f"[{timestamp}] {colored(self.server_username, 'yellow')} ha scritto: {message}")
        
        # notifica che un nuovo utente si è unito
        elif message_data['type'] == 'user_joined':
            timestamp = get_timestamp()
            message = message_data['message']
            
            # aggiunta messaggio alla struttura di log (messaggio di sistema)
            self.add_to_log('system', 'SYSTEM', message, timestamp)
            
            print(f">>> {message}")
            if 'peer_list' in message_data:
                self.peer_list = message_data['peer_list']

        # notifica che un utente ha lasciato la chat
        elif message_data['type'] == 'user_left':
            timestamp = get_timestamp()
            message = message_data['message']
            
            # aggiunta messaggio alla struttura di log (messaggio di sistema)
            self.add_to_log('system', 'SYSTEM', message, timestamp)
            
            print(f">>> {message}")
            if 'peer_list' in message_data:
                self.peer_list = message_data['peer_list']
        
        # il server sta chiudendo la chat
        elif message_data['type'] == 'server_shutdown':
            timestamp = get_timestamp()
            message = message_data['message']
            
            # aggiunta messaggio alla struttura di log (messaggio di sistema)
            self.add_to_log('system', 'SYSTEM', message, timestamp)
            
            print(f">>> {message}")
            return False
        
        return True

    # Funzione chiamata dal client quando rileva che il server si è disconnesso.
    # Avvia la procedura di elezione deterministica tra i client per promuovere un nuovo server.
    def handle_server_disconnect(self):
        if self.promotion_in_progress or self.shutdown_event.is_set(): # se è già in corso una promozione o uno shutdown, non fa nulla
            return
        
        print("Server disconnesso, avvio procedura di elezione...")
        
        self.connected_to_server = False
        
        # se esiste ancora il socket client tenta di chiuderlo
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass # ignora eventuali errori nella chiusura
            self.client_socket = None # rimozione del riferimento al socket client
        
        self.start_leader_election() # avvia la procedura di elezione deterministica per trovare un nuovo server

    # Funzione che avvia un'elezione deterministica per scegliere un nuovo server dopo la disconnessione.
    # Ogni client calcola un ID e attende un tempo proporzionale: chi ha l'ID più basso parte per primo.
    def start_leader_election(self):
        # protegge l'accesso concorrente all'elezione
        with self.election_lock:
            if self.election_in_progress: # se un'elezione è già in corso, non fa nulla
                return
            
            self.election_in_progress = True # segnala che un'elezione è in corso
            self.election_start_time = time.time()
            
            # genera un ID di elezione basato su dati deterministici,
            # questo assicura che tutti i client arrivino alla stessa conclusione
            self.my_election_id = self.generate_election_id()
            
            print(f"Avvio elezione - Il mio ID: {self.my_election_id}")
            
            # aspetta un tempo deterministico per permettere a tutti di calcolare
            election_delay = self.calculate_election_delay()
            
            print(f"Aspetto {election_delay:.2f} secondi per l'elezione...")
            
            # crea un nuovo thread per condurre l'elezione, questo evita di bloccare il thread principale durante l'attesa deterministica
            # e permette al client di restare reattivo (es. ricevere messaggi o gestire lo shutdown)
            election_thread = threading.Thread(
                target=self.conduct_election, 
                args=(election_delay,),
                name="ElectionThread"
            )
            self.add_thread(election_thread) # registra il thread per il cleanup finale
            election_thread.start() # avvia il thread

    # Funzione che genera un ID di elezione deterministico per il client.
    # L’ID è costruito in modo che tutti i client possano calcolarlo nello stesso modo e arrivare alla stessa classifica di priorità.
    def generate_election_id(self):
         # Se il client non ha una peer_list (caso eccezionale), usa un fallback
        if not self.peer_list:
            return hash((self.username, self.connection_time)) # ID grezzo basato su username e orario di connessione
        
        clients = [peer for peer in self.peer_list if not peer.get('is_server', False)] # filtra solo i client (esclude il server)
        clients.sort(key=lambda x: x['connection_time']) # ordina i client in base al momento di connessione
        
        my_position = -1 # inizializza la posizione del client nella lista

        # cerca la posizione del proprio username nella lista ordinata
        for i, client in enumerate(clients):
            if client['username'] == self.username:
                my_position = i
                break
        
        return (my_position, self.connection_time) # restituisce una tupla: posizione nella lista + tempo di connessione

    # Funzione che calcola quanto tempo il client deve aspettare prima di tentare la promozione a server.
    # Il tempo è deterministico e basato sull’ordine di connessione: chi è entrato prima aspetta meno.
    def calculate_election_delay(self):
        if not self.peer_list: # se non c'è una peer list disponibile, restituisce un delay di default
            return 1.0
        
        clients = [peer for peer in self.peer_list if not peer.get('is_server', False)] # filtra solo i peer client (esclude il server)
        
        # il delay è inversamente proporzionale alla priorità: chi ha connection_time più basso ha priorità maggiore
        clients.sort(key=lambda x: x['connection_time']) # ordina i client in base all’ordine di connessione
        
        my_position = -1 # inizializza la posizione corrente del client nella lista ordinata

        # trova la posizione del client nella lista
        for i, client in enumerate(clients):
            if client['username'] == self.username:
                my_position = i
                break
        
        if my_position == -1: # se il client non è stato trovato nella lista (caso anomalo)
            return 5.0  # attende 5 secondi come fallback
        
        return 1.0 + (my_position * 1.0) # chi è primo aspetta 1s, il secondo 2s, ecc.

    # Funzione chiamata quando un nodo rileva la disconnessione del server.
    # Attende un intervallo di tempo determinato (in base alla priorità del nodo),
    # quindi controlla se è il nodo con priorità più alta per diventare server.
    # Se lo è, avvia la procedura di promozione. Altrimenti attende che un altro nodo venga promosso
    # e tenta successivamente la riconnessione.
    def conduct_election(self, delay):
        try:
            # attende il tempo specificato in modo frazionato (0.1s x 10 step = 1s)
            # per poter uscire in anticipo se il sistema è in spegnimento o l'elezione è stata annullata
            for _ in range(int(delay * 10)):
                if self.shutdown_event.is_set() or not self.election_in_progress:
                    return
                time.sleep(0.1)
            
            # recupera il nodo che ha la priorità per diventare server
            next_server = self.get_next_server()
            
            # se questo nodo è il candidato con priorità più alta, si promuove a server
            if next_server and next_server['username'] == self.username:
                print("Sono stato eletto come nuovo server!")
                with self.promotion_lock:
                    if not self.promotion_in_progress:
                        self.promotion_in_progress = True
                        self.promote_to_server()
            # altrimenti aspetta che un altro nodo venga promosso e tenta la riconnessione
            else:
                if next_server:
                    print(f"{next_server['username']} è stato eletto come nuovo server")
                print("Aspetto che il nuovo server si avvii...")
                time.sleep(3) # aspetta un po' di più prima di tentare la riconnessione
                self.attempt_reconnection()
        
        # in caso di errore durante l'elezione, mostra l'eccezione
        except Exception as e:
            print(f"Errore durante l'elezione: {e}")
        finally: # indipendentemente dall'esito, termina lo stato di elezione
            with self.election_lock:
                self.election_in_progress = False

    # Determina chi dovrebbe diventare il prossimo server
    def get_next_server(self):
        # se la peer list è vuota, non ci sono candidati
        if not self.peer_list:
            return None
        
         # seleziona solo i peer che non sono attualmente server
        clients = [peer for peer in self.peer_list if not peer.get('is_server', False)]
        
        # se non ci sono client, nessuno può essere eletto
        if not clients:
            return None
        
        # ordina i client per tempo di connessione (il più vecchio ha priorità)
        clients.sort(key=lambda x: x['connection_time'])
        return clients[0] if clients else None

    # Funzione che promuove il nodo corrente a server
    def promote_to_server(self):
        try:
            print("Avvio promozione a server...")

            self.is_client = False
            self.connected_to_server = False

            # attende un momento per evitare conflitti con altri peer in fase di elezione
            time.sleep(2)

            # genera una lista di porte da provare, partendo dalla porta attuale
            ports_to_try = [self.server_port] + [self.server_port + i for i in range(1, 6)]

            # tenta di avviare il server su ciascuna porta disponibile. Per prima cosa prova la porta originale, 
            # poi le successive. Se l'avvio ha successo interrompe il ciclo e completa la promozione,
            # in caso di fallimento passa alla porta successiva. Se nessuna porta risuta disponibile stampa un messaggio
            # di errore e interrompe l'esecuzione del nodo
            for port in ports_to_try:
                try:
                    success = self.start_as_server(self.server_host, port)
                    if success:
                        print(f"Promozione completata! Server avviato su porta {port}")
                        return
                    else:
                        print(f"Fallito su porta {port}")
                except Exception as e:
                    print(f"Errore su porta {port}: {e}")

            # se tutte le porte falliscono, termina l'esecuzione
            print("Impossibile diventare server su tutte le porte")
            self.running = False

        # gestisce eventuali errori imprevisti durante la promozione
        except Exception as e:
            print(f"Errore durante la promozione: {e}")
            self.running = False
        # resetta i flag di promozione ed elezione, indipendentemente dall’esito
        finally:
            with self.promotion_lock:
                self.promotion_in_progress = False
            with self.election_lock:
                self.election_in_progress = False

    # Tenta di riconnettersi a un nuovo server dopo la disconnessione.
    # Vengono definiti un numero massimo di tentativi (8) e un tempo di attesa iniziale (2s),
    # per ogni tentativo il nodo verifica: 
    #   - se deve uscire dal ciclo e stampa il numero di tentativi
    #   - se riesce a connettersi (su un set di porte ossia quella originale + 5 successive) allora imposta
    #   - il flag di elezione a False e termina
    #   - se tutti i tentativi falliscono, attende un tempo cosi da poter reagire in caso di eventuali eventi di shutdown
    #   - dopo ogni tentativo fallito aumento questo tempo del 20% cosi da evitare di sovraccaricare la rete o il nuovo server
    def attempt_reconnection(self):
        max_attempts = 8    # numero massimo di tentativi di riconnessione
        base_wait = 2       # tempo di attesa iniziale (in secondi) tra i tentativi
        
        for attempt in range(max_attempts):
            if (self.shutdown_event.is_set() or 
                self.promotion_in_progress or 
                self.connected_to_server):
                return
                
            print(f"Tentativo riconnessione {attempt + 1}/{max_attempts}")
            
            # genera una lista di porte da provare per la riconnessione (porta originale + 5 successive)
            ports_to_try = [self.server_port] + [self.server_port + i for i in range(1, 6)]
            
            for port in ports_to_try:
                try:
                    # tenta la connessione a ciascuna porta disponibile
                    if self.connect_as_client(self.server_host, port):
                        print(f"Riconnesso al server sulla porta {port}!")
                        with self.election_lock:
                            self.election_in_progress = False # disattiva lo stato di elezione una volta connesso
                        return
                except:
                    continue
            
            # attende prima del prossimo tentativo, verificando lo stato ogni 100ms
            for _ in range(int(base_wait * 10)):
                if (self.shutdown_event.is_set() or 
                    self.promotion_in_progress or 
                    self.connected_to_server):
                    return
                time.sleep(0.1)
            
            # aumenta progressivamente il tempo di attesa tra i tentativi, fino a un massimo di 8s
            base_wait = min(base_wait * 1.2, 8)
        
        # se tutti i tentativi falliscono, interrompe l'esecuzione del nodo
        print("Impossibile riconnettersi dopo tutti i tentativi")
        self.running = False

    # Funzione eseguita in un thread separato per accettare connessioni dai client.
    # Rimane in ascolto fino a quando il server è attivo e non è stato avviato lo shutdown
    def accept_clients(self):
        # cicla finché il server è attivo e non è in fase di spegnimento
        while self.server_running and self.running and not self.shutdown_event.is_set():
            try:
                client_socket, client_address = self.server_socket.accept() # Accetta una nuova connessione da un client

                # se è stato raggiunto il numero massimo di connessioni rifiuta la connessione altrimenti gestisce il nuovo client
                if len(self.connected_clients) >= self.max_connections: 
                    self.reject_client(client_socket, client_address)
                else:
                    self.handle_new_client(client_socket, client_address)

            except socket.timeout:
                continue  # timeout scaduto, continua il ciclo per accettare nuovi client
            except Exception as e:
                if not self.shutdown_event.is_set(): # evita di stampare l'errore se il server sta chiudendo normalmente
                    print(f"Errore accettazione client: {e}")
                break

    # Funzione (eseguita dal server) che gestisce la ricezione e la redistribuzione dei messaggi da parte di un singolo client.
    # Resta in ascolto fino a quando il server è attivo, il client è connesso, e non è in corso uno shutdown.
    def handle_client_messages(self, client_socket):
        client_info = self.connected_clients.get(client_socket) # recupera le info del client dal dizionario

        # se non esiste, esce subito
        if not client_info:
            return
        
        client_username = client_info['username']
        
        try:
            # ciclo finché il server e il client sono attivi. Mantiene il thread in ascolto continuo finché server e client sono attivi
            while (self.server_running and self.running and 
                   client_socket in self.connected_clients and 
                   not self.shutdown_event.is_set()):
                
                try:
                    client_socket.settimeout(1.0) # imposta timeout per evitare blocchi lunghi, evita che il recv() blocchi il thread per sempre se il client smette di inviare
                    data = client_socket.recv(BUFFER_SIZE).decode('utf-8') # riceve e decodifica i dati
                    client_socket.settimeout(None) # rimuove il timeout dopo la ricezione
                    
                    if not data: # se non arriva nulla, il client è disconnesso quindi in pratica rileva la disconnessione del client
                        break
                    
                    message_data = json.loads(data) # decodifica il messaggio inviato dal client
                    
                    # gestisce solo i messaggi di tipo "chat_message"
                    if message_data['type'] == 'chat_message':
                        timestamp = get_timestamp()
                        message_text = message_data['message']

                        # aggiunge il messaggio alla struttura di log (dal server per i client)
                        self.add_to_log('chat_message', client_username, message_text, timestamp)
                        
                        print(f"[{timestamp}] {colored(client_username, 'yellow')} ha scritto: {message_text}")
                        
                        # invia il messaggio a tutti gli altri client
                        self.broadcast_to_clients({
                            'type': 'chat_message',
                            'username': client_username,
                            'message': message_text,
                            'timestamp': timestamp
                        }, exclude_socket=client_socket)
                
                except socket.timeout:
                    continue # timeout scattato ma nessun dato ricevuto in 1 secondo, ma la connessione è ancora valida. Continua il ciclo
                except socket.error:
                    break # errore di basso livello nella comunicazione socket (es. connessione interrotta). Termina il ciclo per gestire la disconnessione
                except Exception as e:
                    print(f"Errore nel parsing messaggio da {client_username}: {e}")
                    break
        
        # gestisce errori di rete, disconnessioni improvvise o messaggi corrotti
        except Exception as e:
            if self.server_running and not self.shutdown_event.is_set():
                print(f"Errore nella comunicazione con {client_username}: {e}")
        finally:
            # rimuove il client dalla lista quando si disconnette
            self.disconnect_client(client_socket)

    # Gestisce la disconnessione di un client dal server
    def disconnect_client(self, client_socket):
        # controlla se il socket è effettivamente presente nella lista dei client connessi
        if client_socket in self.connected_clients:
            client_info = self.connected_clients[client_socket]
            client_username = client_info['username']

            # rimuove il client dalla lista dei connessi
            del self.connected_clients[client_socket]

            # controllo per vedere se il server non è in fase di shutdown
            if not self.shutdown_event.is_set():
                self.add_to_log('system', 'SYSTEM', f'{client_username} ha lasciato la chat')

                # se non è in corso lo shutdown, stampa un messaggio di disconnessione e mostro il numero aggiornato di client connessi
                print(f">>> {client_username} si è disconnesso")
                self.show_client_count()
                
                # aggiorna la peer list da inviare agli altri client
                peer_list = self.get_peer_list_for_client()
                
                # invia un messaggio di broadcast a tutti i peer per notificare la disconnessione
                self.broadcast_to_clients({
                    'type': 'user_left',
                    'username': client_username,
                    'message': f'{client_username} ha lasciato la chat',
                    'peer_list': peer_list
                })
        
        try:
            client_socket.close() # chiude il socket del client in modo sicuro
        except:
            pass # ignora eventuali errori durante la chiusura del socket

    # Funzione che rifiuta la connessione di un client se il limite massimo è stato raggiunto.
    # Invia un messaggio di rifiuto al client e chiude la connessione.
    def reject_client(self, client_socket, client_address):
        print(f">>> Connessione rifiutata per {client_address[0]}:{client_address[1]} - Limite raggiunto")
        
        try:
            # Invia un messaggio di tipo "join_rejected" al client
            self.send_to_client(client_socket, {
                'type': 'join_rejected',
                'message': f'Chat piena! Massimo {self.max_connections} client consentiti.'
            })
        except:
            pass # Ignora eventuali errori nell'invio del messaggio
        finally:
            client_socket.close() # Chiude comunque la connessione del client

    # Funzione che gestisce l'invio di un messaggio nella chat.
    # Se il nodo è server, invia il messaggio a tutti i client.
    # Se è client, invia il messaggio al server.
    # Restituisce True se l'invio ha successo, False altrimenti.
    def send_message(self, message):
        # verifica se è in corso lo spegnimento in questo caso non invia il messaggio
        if self.shutdown_event.is_set():
            return False
        
        # se chi ha invocato questa funzione è il server, allora invia il messaggio a tutti i client
        if self.is_server:
            # se non ci sono client connessi non invia il messaggio e segnala che non ci sono client connessi
            if not self.connected_clients:
                print("Nessun client connesso!")
                return False
            
            timestamp = get_timestamp()

            # registra nel log locale del server il messaggio inviato
            self.add_to_log('server_message', self.username, message, timestamp)

            # messaggio da inviare a tutti i client
            self.broadcast_to_clients({
                'type': 'server_message',
                'message': message,
                'timestamp': timestamp
            })
            print(f"{colored('Hai scritto', 'blue')}: {message}")
            return True
        
        # se chi ha invocato questa funzione è il client ed è connesso al server, allora invia il messaggio al server
        elif self.is_client and self.connected_to_server:
            try:
                timestamp = get_timestamp()
                # registra nel log locale del client il messaggio che sta per inviare
                self.add_to_log('chat_message', self.username, message, timestamp)

                # crea il messaggio da inviare al server
                message_data = {
                    'type': 'chat_message',
                    'message': message
                }
                self.client_socket.send(json.dumps(message_data).encode('utf-8')) # invia il messaggio al server
                print(f"{colored('Hai scritto', 'blue')}: {message}")
                return True
            # se c'è un errore nell'invio del messaggio, stampa l'errore
            except Exception as e:
                print(f"Errore nell'invio del messaggio: {e}")
                return False
        # se il nodo non è né server né client connesso
        else:
            print("Non connesso a nessuna chat!")
            return False

    # Funzione che invia un messaggio a tutti i client connessi.
    # Se specificato, può escludere un socket (utile ad esempio per non reinviare il messaggio al mittente).
    def broadcast_to_clients(self, message_data, exclude_socket=None):
        # se il nodo non è in modalità server, non invia il messaggio
        if not self.is_server:
            return
        
        message = json.dumps(message_data) # serializza il dizionario in formato JSON
        disconnected_clients = [] # lista per tenere traccia dei client disconnessi
        
        # itera sui socket dei client connessi
        for client_socket in list(self.connected_clients.keys()):
            if client_socket != exclude_socket: # esclude eventualmente un socket specifico (es. mittente)
                try:
                    client_socket.send(message.encode('utf-8')) # invio del messaggio codificato in UTF-8
                except:
                    disconnected_clients.append(client_socket) # registra client da disconnettere in caso di errore

        # Itera sui client disconnessi  e li rimuove dalla lista dei client connessi
        for client_socket in disconnected_clients:
            self.disconnect_client(client_socket)

    # Funzione che invia un messaggio a un singolo client tramite il socket specificato.
    # Il messaggio viene convertito in JSON e inviato come stringa codificata.
    def send_to_client(self, client_socket, message_data):
        try:
            message = json.dumps(message_data)
            client_socket.send(message.encode('utf-8'))
        except Exception as e:
            print(f"Errore nell'invio al client: {e}")

    # Funzione che verifica se un nome utente è già in uso nel sistema (dal server stesso o da uno dei client connessi).
    # Restituisce True se il nome è occupato, False altrimenti.
    def is_username_taken(self, username):
        if username == self.username: # controllo per verificare se il nome utente corrisponde a quello del server
            return True
        
        # itera sulle informazioni di tutti i client connessi
        for client_info in self.connected_clients.values():
            if client_info['username'] == username:
                return True
        return False

    # Funzione che mostra il numero di client attualmente connessi al server.
    def show_client_count(self):
        if self.is_server:
            print(f"Client connessi: {len(self.connected_clients)}/{self.max_connections}")

    def list_connected_users(self):
        if self.is_server:
            if not self.connected_clients:
                print("Nessun client connesso")
            else:
                print("Client connessi:")
                for client_info in self.connected_clients.values():
                    print(f"  • {client_info['username']} ({client_info['address'][0]}:{client_info['address'][1]})")
        elif self.is_client:
            print(f"Connesso al server: {self.server_username}")

    # Funzione che gestisce lo spegnimento ordinato del nodo, sia esso server o client.
    # Chiude connessioni, ferma i thread attivi e libera le risorse.
    def shutdown(self):
        print("\nChiusura in corso...")

        # salvataggio del log della chat in un file di testo
        self.save_chat_log()

        self.running = False # ferma il loop principale del nodo
        self.shutdown_event.set() # segnala a tutti i thread che è in corso lo shutdown
        
        # attendi che l'elezione sia completata prima di procedere,
        # acquisisce il lock per modificare lo stato dell'elezione in corso (entra uno alla volta). Questo serve per evitare
        # che in caso di chiusura avvengano promozioni a server non desiderate o azioni concorrenti
        with self.election_lock:
            self.election_in_progress = False # disattivazione flag di elezione, cioè annulla l’eventuale processo di elezione del leader
        
        # se il nodo è un server ferma il loop del server
        if self.is_server:
            self.server_running = False
            
            # se ci sono client connessi vengono notificati dello shutdown del server
            if self.connected_clients:
                try:
                    self.broadcast_to_clients({
                        'type': 'server_shutdown',
                        'message': 'Il server sta chiudendo la chat'
                    })
                except:
                    pass
            
            # chiude tutte le connessioni client
            for client_socket in list(self.connected_clients.keys()):
                try:
                    client_socket.close()
                except:
                    pass
            self.connected_clients.clear()  # svuota il dizionario dei client connessi
            
            # se il socket del server esiste chiude il socket del server
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
        
        # se esiste il socket del client chiude il socket del client
        elif self.is_client:
            self.connected_to_server = False
            if self.client_socket:
                try:
                    self.client_socket.close()
                except:
                    pass
        
        # pulisce e termina tutti i thread attivi
        self.cleanup_threads()
        
        print("Disconnesso.")