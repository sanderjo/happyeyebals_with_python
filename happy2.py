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
        duration = (time.time() - start) * 1000  # ms
        return {"ip": ip, "port": port, "duration_ms": duration, "success": True, "socket": s}
    except Exception as e:
        duration = (time.time() - start) * 1000  # ms
        return {"ip": ip, "port": port, "duration_ms": duration, "success": False, "error": str(e)}
    finally:
        if not s._closed and not s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
            s.close()

def happy_eyeballs(host, port):
    addresses = resolve_addresses(host, port)
    results = []
    winner = None

    with ThreadPoolExecutor(max_workers=len(addresses)) as executor:
        future_map = {executor.submit(try_connect, fam, ip, port): (fam, ip) for fam, ip, port in addresses}
        
        for future in as_completed(future_map):
            res = future.result()
            results.append(res)

            ip = res['ip']
            time_taken = res['duration_ms']
            status = "SUCCESS" if res['success'] else "FAILURE"
            print(f"[{status}] {ip}:{port} - {time_taken:.2f} ms", end="")
            if not res['success']:
                print(f" ({res['error']})")
            else:
                print()

            if res['success'] and time_taken <= TIMEOUT_MS and not winner:
                winner = res
                # Cancel remaining pending connections
                for f in future_map:
                    if not f.done():
                        f.cancel()
    
    return winner, results

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python happyeyeballs.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    winner, all_results = happy_eyeballs(host, port)

    print("\nSummary of all attempts:")
    for res in all_results:
        ip = res['ip']
        t = res['duration_ms']
        status = "OK" if res['success'] else "FAIL"
        print(f"{ip}:{port} - {t:.2f} ms [{status}]")

    if winner:
        print(f"\nSelected: {winner['ip']}:{winner['port']} in {winner['duration_ms']:.2f} ms")
        winner["socket"].close()
    else:
        print("\nNo connection succeeded within 888 ms.")

