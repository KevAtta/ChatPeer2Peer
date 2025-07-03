from termcolor import colored       # pip install termcolor
import colorama                     # pip install colorama

colorama.init(autoreset=True)       # reset colori dopo ogni print


def print_banner() -> None:
    """Stampa l’intestazione dell’applicazione."""
    line   = "=" * 60
    title  = "CHAT PEER-TO-PEER".center(60)
    print(line)
    print(colored(title, "cyan", attrs=["bold"]))
    print(line)
    print()                         # riga vuota di separazione
