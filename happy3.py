import socket
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, NamedTuple

# Constants
DEF_NETWORKING_TIMEOUT = 888  # milliseconds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

class AddrInfo(NamedTuple):
    family: int
    ip: str
    port: int
    duration_ms: float

def try_connect(family, ip, port, timeout_ms):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(timeout_ms / 1000.0)
    start = time.time()
    try:
        s.connect((ip, port))
        duration = (time.time() - start) * 1000  # to ms
        return {"ip": ip, "port": port, "duration_ms": duration, "success": True, "socket": s, "family": family}
    except Exception as e:
        duration = (time.time() - start) * 1000
        return {"ip": ip, "port": port, "duration_ms": duration, "success": False, "error": str(e), "family": family}
    finally:
        if not s._closed and not s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
            s.close()

def happyeyeballs(
    host: str,
    port: int,
    timeout: int = DEF_NETWORKING_TIMEOUT,
    family=socket.AF_UNSPEC,
) -> Optional[AddrInfo]:
    try:
        infos = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
    except socket.gaierror as e:
        logging.error(f"DNS resolution failed for {host}: {e}")
        return None

    addresses = [(fam, addr[0]) for fam, _, _, _, addr in infos]

    winner = None

    with ThreadPoolExecutor(max_workers=len(addresses)) as executor:
        future_map = {
            executor.submit(try_connect, fam, ip, port, timeout): (fam, ip)
            for fam, ip in addresses
        }

        for future in as_completed(future_map):
            res = future.result()
            ip = res['ip']
            time_taken = res['duration_ms']
            fam = res['family']

            if res['success']:
                logging.info(f"[SUCCESS] {ip}:{port} - {time_taken:.2f} ms (family={fam})")
            else:
                logging.warning(f"[FAILURE] {ip}:{port} - {time_taken:.2f} ms ({res['error']}) (family={fam})")

            if res['success'] and time_taken <= timeout and not winner:
                winner = AddrInfo(family=fam, ip=ip, port=port, duration_ms=time_taken)
                # Cancel remaining
                for f in future_map:
                    if not f.done():
                        f.cancel()

    return winner

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python happyeyeballs.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    result = happyeyeballs(host, port)

    if result:
        logging.info(f"Winner: {result.ip}:{result.port} (family={result.family}) in {result.duration_ms:.2f} ms")
    else:
        logging.error("No connection succeeded within timeout.")
