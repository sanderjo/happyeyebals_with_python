import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

TIMEOUT_MS = 888  # milliseconds

def resolve_addresses(host, port):
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        print(f"DNS resolution failed: {e}")
        sys.exit(1)
    
    return [(family, addr[0], addr[1]) for family, _, _, _, addr in infos]

def try_connect(family, ip, port):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT_MS / 1000.0)
    start = time.time()
    try:
        s.connect((ip, port))
        duration = (time.time() - start) * 1000  # to ms
        return {"ip": ip, "port": port, "duration_ms": duration, "socket": s}
    except Exception:
        s.close()
        return None

def happy_eyeballs(host, port):
    addresses = resolve_addresses(host, port)
    results = []
    with ThreadPoolExecutor(max_workers=len(addresses)) as executor:
        future_map = {executor.submit(try_connect, fam, ip, port): (fam, ip) for fam, ip, port in addresses}
        for future in as_completed(future_map):
            res = future.result()
            if res and res["duration_ms"] <= TIMEOUT_MS:
                # Close other connections
                for f in future_map:
                    if f != future:
                        f.cancel()
                return res
    return None

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python happyeyeballs.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    result = happy_eyeballs(host, port)
    if result:
        print(f"Connected to {result['ip']}:{result['port']} in {result['duration_ms']:.2f} ms")
        result["socket"].close()
    else:
        print("No connection succeeded within 888 ms.")

