#!/usr/bin/env python3
"""
F11 Video Link Extractor - Pop-Under Killer Edition
Kaçak film/dizi sitelerinden asıl video linklerini (mp4, m3u8) çıkartır.
Pop-under reklam tuzaklarını otomatik olarak engeller.
"""

import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
import argparse
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
    MAGENTA = "\033[95m"


class VideoLinkExtractor:
    """Kaçak sitelerden video linklerini çıkartır ve pop-under'ları engeller."""
    
    # Video dosya uzantıları
    VIDEO_EXTENSIONS = {'.m3u8', '.mp4', '.ts', '.mpd', '.m4s', '.webm', '.mov', '.avi', '.m4v'}
    
    # Video kaynağını işaret eden kritik anahtar kelimeler
    VIDEO_KEYWORDS = {
        'vidsrc', 'master.m3u8', 'playlist.m3u8', 'stream', 
        'video', 'source', 'manifest', 'hls', 'dash', 'media',
        'cdn', 'content', 'playback', '.m3u8', '.mp4'
    }
    
    def __init__(self, url: str, timeout: int = 60000):
        self.url = url
        self.timeout = timeout
        self.video_links = set()  # Duplikasyonu önlemek için set
        self.browser = None
        self.context = None
        self.page = None
    
    def is_video_link(self, url: str) -> bool:
        """URL'nin video linki olup olmadığını kontrol et."""
        url_lower = url.lower()
        
        # Uzantı kontrolü
        for ext in self.VIDEO_EXTENSIONS:
            if url_lower.endswith(ext):
                return True
        
        # Anahtar kelime kontrolü
        for keyword in self.VIDEO_KEYWORDS:
            if keyword in url_lower:
                return True
        
        return False
    
    def print_video_found(self, url: str):
        """Video linki bulunduğunda konsolda göster."""
        if url not in self.video_links:  # Duplikasyonu kontrol et
            self.video_links.add(url)
            print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*80}")
            print(f"🎬 ASIL VİDEO LİNKİ YAKALANDI!")
            print(f"{'='*80}{Colors.RESET}")
            print(f"{Colors.GREEN}{Colors.BOLD}{url}{Colors.RESET}\n")
    
    async def handle_popup(self, context: BrowserContext):
        """Pop-under sayfalarını otomatik olarak kapat."""
        async def on_page(popup_page: Page):
            try:
                popup_url = popup_page.url
                print(f"{Colors.RED}[💥 POP-UNDER ENGELLENDİ] {popup_url}{Colors.RESET}")
                await popup_page.close()
            except:
                pass
        
        context.on("page", on_page)
    
    async def simulate_clicks(self):
        """Sayfanın merkezine otomatik tıklamalar yap (görünmez katmanları patlatmak için)."""
        try:
            # DOM içeriği yüklensin diye bekle
            await asyncio.sleep(2)
            
            # Viewport boyutlarını al
            viewport = self.page.viewportsize
            if not viewport:
                print(f"{Colors.YELLOW}⚠️ Viewport bilgisi alınamadı.{Colors.RESET}")
                return
            
            center_x = viewport['width'] / 2
            center_y = viewport['height'] / 2
            
            print(f"{Colors.CYAN}🖱️ Otomatik tıklamalar simüle ediliyor... ({int(center_x)}, {int(center_y)}){Colors.RESET}")
            
            # 3 kez 1 saniye arayla tıkla
            for i in range(3):
                try:
                    await self.page.mouse.click(center_x, center_y)
                    await asyncio.sleep(1)
                    print(f"{Colors.CYAN}  └─ Tıklama {i+1}/3 yapıldı{Colors.RESET}")
                except:
                    pass
        
        except Exception as e:
            print(f"{Colors.YELLOW}⚠️ Tıklama simülasyonu hata: {e}{Colors.RESET}")
    
    async def extract(self):
        """Ana çıkartma işlemini başlat."""
        try:
            async with async_playwright() as p:
                # Headless modu kapat, tarayıcı penceresini göster
                self.browser = await p.chromium.launch(headless=True)
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()
                
                # Pop-under engelleyiciyi kur
                await self.handle_popup(self.context)
                
                # Video linklerini yakala
                async def on_response(response):
                    try:
                        url = response.url
                        if self.is_video_link(url):
                            self.print_video_found(url)
                    except:
                        pass
                
                self.page.on("response", on_response)
                
                try:
                    print(f"{Colors.BOLD}{Colors.BLUE}🚀 Sayfa yükleniyor: {self.url}{Colors.RESET}")
                    # wait_until="load" daha hızlı, networkidle yerine
                    await self.page.goto(self.url, wait_until="load", timeout=self.timeout)
                    print(f"{Colors.CYAN}✓ Sayfa yüklendi, tarama başladı...{Colors.RESET}")
                    
                    # Otomatik tıklamalar simüle et
                    await self.simulate_clicks()
                    
                    # Ek bekleme (dinamik video yüklemeleri için)
                    print(f"{Colors.CYAN}⏳ Dinamik içerik yüklemesi bekleniyor...{Colors.RESET}")
                    await asyncio.sleep(5)
                    
                    print(f"{Colors.GREEN}✅ Tarama tamamlandı.{Colors.RESET}")
                    
                except asyncio.TimeoutError:
                    print(f"{Colors.YELLOW}⚠️ Timeout! Tarama devam ediyor...{Colors.RESET}")
                    # Timeout'tan sonra da biraz daha bekle
                    await self.simulate_clicks()
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    print(f"{Colors.RED}❌ Sayfa yükleme hatası: {str(e)[:100]}{Colors.RESET}")
                
                # Kaynakları temizle
                try:
                    await self.page.close()
                except:
                    pass
                try:
                    await self.context.close()
                except:
                    pass
                try:
                    await self.browser.close()
                except:
                    pass
                    
        except Exception as e:
            print(f"{Colors.RED}❌ Kritik hata: {str(e)[:100]}{Colors.RESET}")
    
    def show_results(self):
        """Bulduğu video linklerini göster."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}{'='*80}")
        print(f"📊 SONUÇLAR")
        print(f"{'='*80}{Colors.RESET}")
        
        if not self.video_links:
            print(f"{Colors.YELLOW}⚠️ Video linki bulunamadı.{Colors.RESET}")
        else:
            video_list = sorted(list(self.video_links))
            print(f"{Colors.GREEN}Bulunan {len(video_list)} video linki:{Colors.RESET}\n")
            for i, link in enumerate(video_list, 1):
                # URL'yi 100 karakterle sınırla
                display_link = link if len(link) <= 100 else link[:97] + "..."
                print(f"{Colors.GREEN}{i}. {display_link}{Colors.RESET}")


async def main():
    parser = argparse.ArgumentParser(
        description='F11 Video Link Extractor - Kaçak sitelerden video linklerini çıkartır',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnek:
  python file1.py "https://cizgivedizi.com/dizi/..."
  python file1.py "https://site.com" -t 90000
        """
    )
    parser.add_argument('url', nargs='?', help='İzlenecek URL')
    parser.add_argument('-t', '--timeout', default=60000, type=int, help='Timeout (ms, varsayılan: 60000)')
    
    args = parser.parse_args()
    
    url = args.url
    if not url:
        url = input(f"{Colors.CYAN}İzlemek istediğiniz URL: {Colors.RESET}").strip()
    
    if not url:
        print(f"{Colors.RED}❌ URL gerekli!{Colors.RESET}")
        sys.exit(1)
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    extractor = VideoLinkExtractor(url, timeout=args.timeout)
    await extractor.extract()
    extractor.show_results()
    
    # Kullanıcı girişini bekle
    print(f"\n{Colors.CYAN}Videoyu manuel oynatmak için Enter'e basın...{Colors.RESET}")
    try:
        await asyncio.to_thread(input)
    except (KeyboardInterrupt, EOFError):
        pass
    
    print(f"{Colors.YELLOW}Kapatılıyor...{Colors.RESET}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}İptal edildi.{Colors.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}Beklenmeyen hata: {e}{Colors.RESET}")
        sys.exit(1)
