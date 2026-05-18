#!/usr/bin/env python3
"""
F11 Ağ İzleyici - Akıllı Link Filtrelemeli Versiyon
100 karakterden uzun URL'ler ekranda gizlenir, dosyalarda tam kaydedilir.

İyileştirmeler:
- Type hints eklendi
- Hata yönetimi geliştirildi
- DRY prensibi uygulandı
- Code cleanup
"""

from playwright.sync_api import sync_playwright, Page, Response, Request
import argparse
import csv
import json
import time
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any
import sys

# --- RENK TANIMLAMALARI ---
class Colors:
    """ANSI renk kodları"""
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    MAGENTA = "\033[95m"

    @staticmethod
    def get_all_colors() -> Dict[str, str]:
        """Tüm renkleri dict olarak döndür"""
        return {
            name: getattr(Colors, name)
            for name in dir(Colors)
            if not name.startswith('_') and name.isupper() and name != 'RESET'
        }


def renkle_durum(status: int) -> str:
    """Status kodunu renglendir"""
    if 200 <= status < 300:
        return f"{Colors.GREEN}{status}{Colors.RESET}"
    elif 400 <= status < 500:
        return f"{Colors.YELLOW}{status}{Colors.RESET}"
    elif status >= 500:
        return f"{Colors.RED}{status}{Colors.RESET}"
    else:
        return f"{Colors.CYAN}{status}{Colors.RESET}"


def renkle_metot(method: str) -> str:
    """HTTP metodunu renglendir"""
    color_map = {
        "GET": Colors.BLUE,
        "POST": Colors.GREEN,
        "PUT": Colors.YELLOW,
        "DELETE": Colors.YELLOW,
        "PATCH": Colors.YELLOW,
        "WS": Colors.RED + Colors.BOLD,
    }
    color = color_map.get(method, Colors.CYAN)
    return f"{color}{method}{Colors.RESET}"


def renkle_tip(tip: str) -> str:
    """Kaynak türünü renglendir"""
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


def format_display_url(url: str, max_length: int = 100) -> str:
    """URL'yi ekrana göstermek için formatla (DRY prensip)"""
    if len(url) > max_length:
        return f"{Colors.RED}[UZUN URL GİZLENDİ]{Colors.RESET}"
    return url


def format_file_size(size_bytes: Optional[str]) -> str:
    """Dosya boyutunu format et"""
    if not size_bytes:
        return "-"
    try:
        return f"{int(size_bytes) / 1024:.1f} KB"
    except (ValueError, TypeError):
        return "-"


def get_table_width() -> int:
    """Tablo genişliğini hesapla"""
    return 7 + 3 + 6 + 3 + 10 + 3 + 12 + 3 + 25 + 3 + 100  # 175 karaktere sadeleştiriyoruz


def print_table_header() -> None:
    """Tablo başlığını yazdır"""
    header = f"{'METOT':<7} | {'DURUM':<6} | {'SÜRE (ms)':<10} | {'TÜR':<12} | {'DOMAIN':<25} | {'URL':<60}"
    print(header)
    print("-" * len(header))


def print_table_row(
    method_colored: str,
    status_colored: str,
    duration_ms: int,
    type_colored: str,
    domain: str,
    display_url: str,
    error_marker: str = ""
) -> None:
    """Tablo satırını yazdır"""
    print(f"{method_colored:<7} | {status_colored:<6} | {duration_ms:<10} | "
          f"{type_colored:<12} | {domain:<25} | {display_url:<60}{error_marker}")


def network_izle(
    url: str,
    output_csv: Optional[str] = None,
    output_json: Optional[str] = None,
    timeout: int = 30000,
    verbose: bool = True,
    max_headers: int = 50
) -> List[Dict[str, Any]]:
    """
    Web sayfasının ağ trafiğini izle
    
    Args:
        url: İzlenecek web sayfasının URL'si
        output_csv: CSV çıktı dosyası yolu
        output_json: JSON çıktı dosyası yolu
        timeout: Timeout süresi (ms)
        verbose: Verbose mod
        max_headers: Saklanacak maksimum header sayısı
    
    Returns:
        Network istekleri listesi
    """
    results: List[Dict[str, Any]] = []
    start_time = time.time()
    request_times: Dict[str, float] = {}
    
    print(f"{Colors.BOLD}📡 Ağ İzleme Başlatılıyor...{Colors.RESET}")
    print(f"Hedef: {url}")
    print_table_header()

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                print(f"{Colors.RED}❌ Chromium başlatılamadı: {e}{Colors.RESET}")
                print("Lütfen 'playwright install' komutunu çalıştırın.")
                return []
            
            page = browser.new_page()

            def on_request(request: Request) -> None:
                """Request hook"""
                request_times[request.url] = time.time()

            def on_response(response: Response) -> None:
                """Response hook"""
                request = response.request
                url_full = response.url
                
                start = request_times.get(url_full, time.time())
                duration_ms = int((time.time() - start) * 1000)
                
                status = response.status
                method = request.method
                resource_type = request.resource_type
                domain = urlparse(url_full).netloc or "Direct"
                
                size_str = format_file_size(response.header_value('content-length'))
                is_error = status >= 400
                
                # Header sayısını sınırla (Performance için)
                response_headers = dict(list(response.all_headers().items())[:max_headers])
                request_headers = dict(list(request.headers.items())[:max_headers])
                
                result: Dict[str, Any] = {
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
                    'request_headers': request_headers,
                    'response_headers': response_headers
                }
                results.append(result)
                
                if verbose:
                    status_colored = renkle_durum(status)
                    method_colored = renkle_metot(method)
                    type_colored = renkle_tip(resource_type)
                    error_marker = " ⚠️" if is_error else ""
                    display_url = format_display_url(url_full, max_length=60)
                    
                    print_table_row(
                        method_colored,
                        status_colored,
                        duration_ms,
                        type_colored,
                        domain,
                        display_url,
                        error_marker
                    )

            def on_websocket(ws) -> None:
                """WebSocket hook"""
                ws_url = ws.url
                domain = urlparse(ws_url).netloc
                result: Dict[str, Any] = {
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
                    display_ws = format_display_url(ws_url, max_length=60)
                    print_table_row(
                        renkle_metot('WS'),
                        renkle_durum(101),
                        0,
                        renkle_tip('websocket'),
                        domain,
                        display_ws
                    )

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("websocket", on_websocket)

            try:
                page.goto(url, wait_until="networkidle", timeout=timeout)
                elapsed_total = time.time() - start_time
                print(f"\n{Colors.GREEN}✅ Sayfa yüklemesi tamamlandı.{Colors.RESET} "
                      f"Toplam süre: {elapsed_total:.2f}s")
            except TimeoutError:
                print(f"\n{Colors.YELLOW}⏱️ Timeout süresi aşıldı ({timeout}ms){Colors.RESET}")
            except Exception as e:
                print(f"\n{Colors.RED}❌ Hata oluştu: {e}{Colors.RESET}")
            finally:
                browser.close()

    except Exception as e:
        print(f"{Colors.RED}❌ Beklenmeyen hata: {e}{Colors.RESET}")
        return []

    # --- İSTATİSTİKLER ---
    _print_statistics(results)

    # --- DOSYA KAYDETME ---
    _save_results(results, output_csv, output_json)

    return results


def _print_statistics(results: List[Dict[str, Any]]) -> None:
    """İstatistikleri yazdır"""
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
        error_rate = (error_count / total_requests) * 100
        print(f"{Colors.RED}⚠️ Hata oranı: {error_rate:.1f}%{Colors.RESET}")
    
    print(f"\nEn çok kullanılan Domainler:")
    for domain, count in domain_counter.most_common(5):
        print(f"  - {domain}: {count} istek")
    
    print(f"\nKaynak Türleri Dağılımı:")
    for typ, count in type_counter.most_common():
        print(f"  - {renkle_tip(typ)}: {count}")


def _save_results(
    results: List[Dict[str, Any]],
    output_csv: Optional[str] = None,
    output_json: Optional[str] = None
) -> None:
    """Sonuçları dosyalara kaydet"""
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


def main() -> None:
    """Ana fonksiyon"""
    parser = argparse.ArgumentParser(
        description='Akıllı Web Ağ İzleyici - Uzun URL Filtrelemeli',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Örnekler:\n"
               "  python file1_improved.py https://example.com\n"
               "  python file1_improved.py example.com -o network.csv --json network.json\n"
               "  python file1_improved.py -q --json output.json"
    )
    parser.add_argument('url', nargs='?', help='İzlenecek URL')
    parser.add_argument('-o', '--csv', dest='output_csv', help='CSV dosyasına kaydet')
    parser.add_argument('--json', dest='output_json', help='JSON dosyasına kaydet')
    parser.add_argument('-t', '--timeout', default=30000, type=int, help='Timeout (ms), default: 30000')
    parser.add_argument('-q', '--quiet', action='store_true', help='Sessiz mod')
    
    args = parser.parse_args()
    
    url = args.url
    if not url:
        try:
            url = input("İzlemek istediğiniz URL: ").strip()
        except KeyboardInterrupt:
            print(f"\n{Colors.RED}İşlem iptal edildi.{Colors.RESET}")
            sys.exit(1)
    
    if not url:
        parser.error("URL belirtilmelidir!")
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    network_izle(
        url=url,
        output_csv=args.output_csv,
        output_json=args.output_json,
        timeout=args.timeout,
        verbose=not args.quiet
    )


if __name__ == "__main__":
    main()
