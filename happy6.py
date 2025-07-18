import socket
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, NamedTuple, List, Tuple

DEF_NETWORKING_TIMEOUT = 888  # ms
DNS_TIMEOUT = 4  # seconds

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
    hostname: str

IPV6_MAPPING = {
    "news.eweka.nl": "news6.eweka.nl",
    "news.xlned.com": "news6.xlned.com",
    "news.easynews.com": "news6.easynews.com",
    "news.tweaknews.nl": "news6.tweaknews.nl",
    "news.tweaknews.eu": "news6.tweaknews.eu",
    "news.astraweb.com": "news6.astraweb.com",
    "news.pureusenet.nl": "news6.pureusenet.nl",
    "news.sunnyusenet.com": "news6.sunnyusenet.com",
    "news.newshosting.com": "news6.newshosting.com",
    "news.usenetserver.com": "news6.usenetserver.com",
    "news.frugalusenet.com": "news-v6.frugalusenet.com",
    "eunews.frugalusenet.com": "eunews-v6.frugalusenet.com",
}

def try_connect(family, ip, port, timeout_ms, hostname):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(timeout_ms / 1000.0)
    start = time.time()
    try:
        s.connect((ip, port))
        duration = (time.time() - start) * 1000
        return {"ip": ip, "port": port, "duration_ms": duration, "success": True, "family": family, "hostname": hostname}
    except Exception as e:
        duration = (time.time() - start) * 1000
        return {"ip": ip, "port": port, "duration_ms": duration, "success": False, "error": str(e), "family": family, "hostname": hostname}
    finally:
        if not s._closed and not s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
            s.close()

def resolve_addresses(host: str, port: int, family, dns_timeout=DNS_TIMEOUT) -> List[Tuple[int, str]]:
    def _resolve():
        return socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_resolve)
        try:
            infos = future.result(timeout=dns_timeout)
            return [(fam, addr[0]) for fam, _, _, _, addr in infos]
        except Exception as e:
            logging.error(f"DNS resolution failed for {host}: {e}")
            return []

def happyeyeballs(
    host: str,
    port: int,
    timeout: int = DEF_NETWORKING_TIMEOUT,
    family=socket.AF_UNSPEC,
) -> Optional[AddrInfo]:

    hosts_to_try = [host]
    if host in IPV6_MAPPING:
        hosts_to_try.append(IPV6_MAPPING[host])

    all_addresses = []
    for h in hosts_to_try:
        resolved = resolve_addresses(h, port, family)
        for fam, ip in resolved:
            all_addresses.append((fam, ip, h))

    if not all_addresses:
        logging.error(f"No addresses resolved for {hosts_to_try}")
        return None

    with ThreadPoolExecutor(max_workers=len(all_addresses)) as executor:
        future_map = {
            executor.submit(try_connect, fam, ip, port, timeout, h): (fam, ip, h)
            for fam, ip, h in all_addresses
        }

        for future in as_completed(future_map):
            res = future.result()
            ip = res['ip']
            time_taken = res['duration_ms']
            fam = res['family']
            h = res['hostname']

            if res['success']:
                logging.info(f"[SUCCESS] {h} -> {ip}:{port} - {time_taken:.2f} ms (family={fam})")
                # Cancel other pending futures
                executor.shutdown(cancel_futures=True)
                return AddrInfo(family=fam, ip=ip, port=port, duration_ms=time_taken, hostname=h)
            else:
                logging.warning(f"[FAILURE] {h} -> {ip}:{port} - {time_taken:.2f} ms ({res['error']}) (family={fam})")

    return None

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python happyeyeballs.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    result = happyeyeballs(host, port)

    if result:
        logging.info(f"Winner: {result.hostname} -> {result.ip}:{result.port} (family={result.family}) in {result.duration_ms:.2f} ms")
    else:
        logging.error("No connection succeeded within timeout.")
