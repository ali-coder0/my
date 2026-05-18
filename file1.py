#!/usr/bin/env python3
"""
F11 Ağ İzleyici - Akıllı Link Filtrelemeli Versiyon
100 karakterden uzun URL'ler ekranda gizlenir, dosyalarda tam kaydedilir.
"""

from playwright.sync_api import sync_playwright, Page, Response, Request
import argparse
import csv
import json
import time
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse
import sys

# --- RENK TANIMLAMALARI ---
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    MAGENTA = "\033[95m" if '\033[95m' in '\033[95m' else "\033[96m" 

def renkle_durum(status):
    if 200 <= status < 300: return f"{Colors.GREEN}{status}{Colors.RESET}"
    elif 400 <= status < 500: return f"{Colors.YELLOW}{status}{Colors.RESET}"
    elif status >= 500: return f"{Colors.RED}{status}{Colors.RESET}"
    else: return f"{Colors.CYAN}{status}{Colors.RESET}"

def renkle_metot(method):
    if method == "GET": return f"{Colors.BLUE}{method}{Colors.RESET}"
    elif method == "POST": return f"{Colors.GREEN}{method}{Colors.RESET}"
    elif method in ["PUT", "DELETE", "PATCH"]: return f"{Colors.YELLOW}{method}{Colors.RESET}"
    else: return f"{Colors.CYAN}{method}{Colors.RESET}"

def renkle_tip(tip):
    tip = tip.lower()
    colors = {
        'document': f"{Colors.BOLD}{Colors.WHITE}",
        'stylesheet': f"{Colors.BLUE}",
        'script': f"{Colors.YELLOW}",
        'image': f"{Colors.CYAN}",
        'font': f"{Colors.MAGENTA}",
        'xhr': f"{Colors.GREEN}",
        'fetch': f"{Colors.GREEN}",
        'websocket': f"{Colors.RED}{Colors.BOLD}",
        'media': f"{Colors.WHITE}",
        'ping': f"{Colors.CYAN}",
        'csp_report': f"{Colors.WHITE}",
        'manifest': f"{Colors.WHITE}",
        'other': f"{Colors.WHITE}"
    }
    color_code = colors.get(tip, colors['other'])
    return f"{color_code}{tip.upper()}{Colors.RESET}"

def network_izle(url, output_csv=None, output_json=None, timeout=30000, verbose=True):
    results = []
    start_time = time.time()
    
    print(f"{Colors.BOLD}📡 Ağ İzleme Başlatılıyor...{Colors.RESET}")
    print(f"Hedef: {url}")
    # Tablo başlığı
    print(f"{'METOT':<7} | {'DURUM':<6} | {'SÜRE (ms)':<10} | {'TÜR':<12} | {'DOMAIN':<25} | {'URL (Max 100 char)'}")
    print("-" * 110)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        request_times = {}

        def on_request(request: Request):
            request_times[request.url] = time.time()

        def on_response(response: Response):
            request = response.request
            url_full = response.url
            
            start = request_times.get(url_full, time.time())
            duration_ms = int((time.time() - start) * 1000)
            
            status = response.status
            method = request.method
            resource_type = request.resource_type
            domain = urlparse(url_full).netloc or "Direct"
            
            size = response.header_value('content-length')
            size_str = f"{int(size)/1024:.1f} KB" if size else "-"
            is_error = status >= 400
            
            # Sonuç sözlüğü (Tüm veriler burada tam olarak saklanır)
            result = {
                'timestamp': datetime.now().isoformat(),
                'method': method,
                'status': status,
                'duration_ms': duration_ms,
                'type': resource_type,
                'domain': domain,
                'url': url_full,  # Tam URL dosyaya kaydedilecek
                'size': size_str,
                'is_error': is_error,
                'headers_count': len(response.all_headers()),
                'request_headers': dict(request.headers),
                'response_headers': dict(response.all_headers())
            }
            results.append(result)
            
            if verbose:
                status_colored = renkle_durum(status)
                method_colored = renkle_metot(method)
                type_colored = renkle_tip(resource_type)
                error_marker = " ⚠️ " if is_error else ""
                
                # --- AKILLI FİLTRELEME ---
                # Eğer URL 100 karakterden uzunsa ekranda gösterme
                if len(url_full) > 100:
                    display_url = f"{Colors.RED}[UZUN URL GİZLENDİ]{Colors.RESET}"
                else:
                    display_url = url_full
                
                print(f"{method_colored:<7} | {status_colored:<6} | {duration_ms:<10} | {type_colored:<12} | {domain:<25} | {display_url}{error_marker}")

        def on_websocket(ws):
            ws_url = ws.url
            domain = urlparse(ws_url).netloc
            result = {
                'timestamp': datetime.now().isoformat(),
                'method': 'WEBSOCKET',
                'status': 101, 
                'duration_ms': 0,
                'type': 'websocket',
                'domain': domain,
                'url': ws_url,
                'size': '-',
                'is_error': False,
                'headers_count': 0,
                'request_headers': {},
                'response_headers': {}
            }
            results.append(result)
            if verbose:
                if len(ws_url) > 100:
                    display_ws = f"{Colors.RED}[UZUN WS GİZLENDİ]{Colors.RESET}"
                else:
                    display_ws = ws_url
                print(f"{renkle_metot('WS'):<7} | {renkle_durum(101):<6} | {'-':<10} | {renkle_tip('websocket'):<12} | {domain:<25} | {display_ws}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("websocket", on_websocket)

        try:
            page.goto(url, wait_until="networkidle", timeout=timeout)
            elapsed_total = time.time() - start_time
            print(f"\n{Colors.GREEN}✅ Sayfa yüklemesi tamamlandı.{Colors.RESET} Toplam süre: {elapsed_total:.2f}s")
        except Exception as e:
            print(f"\n{Colors.RED}❌ Hata oluştu: {e}{Colors.RESET}")

        browser.close()

    # --- İSTATİSTİKLER ---
    total_requests = len(results)
    error_count = sum(1 for r in results if r['is_error'])
    success_count = total_requests - error_count
    
    domain_counter = Counter(r['domain'] for r in results)
    type_counter = Counter(r['type'] for r in results)
    
    print(f"\n{Colors.BOLD}📊 Özet Rapor{Colors.RESET}")
    print(f"Toplam İstek: {total_requests}")
    print(f"Başarılı (2xx): {success_count}")
    print(f"Hatalı (4xx/5xx): {error_count}")
    if error_count > 0:
        print(f"{Colors.RED}⚠️ Hata oranı: {(error_count/total_requests)*100:.1f}%{Colors.RESET}")
    
    print(f"\nEn çok kullanılan Domainler:")
    for domain, count in domain_counter.most_common(5):
        print(f"  - {domain}: {count} istek")
    
    print(f"\nKaynak Türleri Dağılımı:")
    for typ, count in type_counter.most_common():
        print(f"  - {renkle_tip(typ)}: {count}")

    # --- DOSYA KAYDETME (Her zaman TAM URL ile) ---
    if output_csv:
        try:
            with open(output_csv, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp', 'method', 'status', 'duration_ms', 'type', 'domain', 'url', 'size', 'is_error']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in results:
                    writer.writerow({k: r[k] for k in fieldnames})
            print(f"\n{Colors.GREEN}📁 CSV kaydedildi: {output_csv}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}❌ CSV kaydetme hatası: {e}{Colors.RESET}")

    if output_json:
        try:
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"{Colors.GREEN}📁 JSON kaydedildi: {output_json}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}❌ JSON kaydetme hatası: {e}{Colors.RESET}")

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Akıllı Web Ağ İzleyici - Uzun URL Filtrelemeli')
    parser.add_argument('url', nargs='?', help='İzlenecek URL')
    parser.add_argument('-o', '--csv', dest='output_csv', help='CSV dosyasına kaydet')
    parser.add_argument('--json', dest='output_json', help='JSON dosyasına kaydet')
    parser.add_argument('-t', '--timeout', default=30000, type=int, help='Timeout (ms)')
    parser.add_argument('-q', '--quiet', action='store_true', help='Sessiz mod')
    
    args = parser.parse_args()
    
    url = args.url
    if not url:
        url = input("İzlemek istediğiniz URL: ").strip()
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    network_izle(
        url=url,
        output_csv=args.output_csv,
        output_json=args.output_json,
        timeout=args.timeout,
        verbose=not args.quiet
    )
