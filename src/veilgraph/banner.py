"""Banner ASCII do VeilGraph.

Uso:
    from veilgraph.banner import BANNER, print_banner
    print_banner()          # colorido (se o terminal suportar)
"""

RESET = "\033[0m"
PURPLE = "\033[38;5;141m"
DIM = "\033[38;5;244m"
CYAN = "\033[38;5;81m"

LOGO = r"""
██╗   ██╗███████╗██╗██╗     ██████╗ ██████╗  █████╗ ██████╗ ██╗  ██╗
██║   ██║██╔════╝██║██║     ██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██║  ██║
██║   ██║█████╗  ██║██║     ██║  ███╗██████╔╝███████║██████╔╝███████║
╚██╗ ██╔╝██╔══╝  ██║██║     ██║   ██║██╔══██╗██╔══██║██╔═══╝ ██╔══██║
 ╚████╔╝ ███████╗██║███████╗╚██████╔╝██║  ██║██║  ██║██║     ██║  ██║
  ╚═══╝  ╚══════╝╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝
"""

TAGLINE = "  on-chain graph analyzer · privacy/obfuscation simulator"
WARNING = "  ⚠  read-only — nenhuma transação é criada ou enviada"


def print_banner(color: bool = True) -> None:
    logo = LOGO
    if color:
        logo = f"{PURPLE}{LOGO}{RESET}"
        tag = f"{CYAN}{TAGLINE}{RESET}"
        warn = f"{DIM}{WARNING}{RESET}"
    else:
        tag, warn = TAGLINE, WARNING
    print(logo)
    print(tag)
    print(warn)
    print()


BANNER = LOGO
