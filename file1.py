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
    VIDEO_EXTENSIONS = {'.m3u8', '.mp4', '.ts', '.mpd', '.m4s', '.webm', '.mov', '.avi'}
    
    # Video kaynağını işaret eden kritik anahtar kelimeler
    VIDEO_KEYWORDS = {
        'vidsrc', 'master.m3u8', 'playlist.m3u8', 'stream', 
        'video', 'source', 'manifest', 'hls', 'dash', 'media',
        'cdn', 'content', 'playback'
    }
    
    def __init__(self, url: str, timeout: int = 30000):
        self.url = url
        self.timeout = timeout
        self.video_links = []
        self.browser = None
        self.context = None
        self.page = None
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
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
        print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*80}")
        print(f"🎬 ASIL VİDEO LİNKİ YAKALANDI!")
        print(f"{'='*80}{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD}{url}{Colors.RESET}\n")
        self.video_links.append(url)
    
    async def handle_popup(self, context: BrowserContext):
        """Pop-under sayfalarını otomatik olarak kapat."""
        async def on_page(popup_page: Page):
            popup_url = popup_page.url
            print(f"{Colors.RED}[💥 POP-UNDER ENGELLENDİ] {popup_url}{Colors.RESET}")
            await popup_page.close()
        
        context.on("page", on_page)
    
    async def simulate_clicks(self):
        """Sayfanın merkezine otomatik tıklamalar yap (görünmez katmanları patlatmak için)."""
        try:
            # DOM içeriği yüklensin diye bekle
            await asyncio.sleep(3)
            
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
                await self.page.mouse.click(center_x, center_y)
                await asyncio.sleep(1)
                print(f"{Colors.CYAN}  └─ Tıklama {i+1}/3 yapıldı{Colors.RESET}")
        
        except Exception as e:
            print(f"{Colors.YELLOW}⚠️ Tıklama simülasyonu hata: {e}{Colors.RESET}")
    
    async def extract(self):
        """Ana çıkartma işlemini başlat."""
        async with async_playwright() as p:
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
                except Exception as e:
                    pass
            
            self.page.on("response", on_response)
            
            try:
                print(f"{Colors.BOLD}{Colors.BLUE}🚀 Sayfa yükleniyor: {self.url}{Colors.RESET}")
                await self.page.goto(self.url, wait_until="domcontentloaded", timeout=self.timeout)
                
                # Otomatik tıklamalar simüle et
                await self.simulate_clicks()
                
                # Ek bekleme (dinamik video yüklemeleri için)
                await asyncio.sleep(3)
                
                print(f"{Colors.GREEN}✅ Tarama tamamlandı.{Colors.RESET}")
                
            except Exception as e:
                print(f"{Colors.RED}❌ Sayfa yükleme hatası: {e}{Colors.RESET}")
            
            await self.cleanup()
    
    async def cleanup(self):
        """Kaynakları temizle."""
        if self.page:
            try:
                await self.page.close()
            except:
                pass
        if self.context:
            try:
                await self.context.close()
            except:
                pass
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
    
    def show_results(self):
        """Bulduğu video linklerini göster."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}{'='*80}")
        print(f"📊 SONUÇLAR")
        print(f"{'='*80}{Colors.RESET}")
        
        if not self.video_links:
            print(f"{Colors.YELLOW}⚠️ Video linki bulunamadı.{Colors.RESET}")
        else:
            print(f"{Colors.GREEN}Bulunan {len(self.video_links)} video linki:{Colors.RESET}\n")
            for i, link in enumerate(self.video_links, 1):
                print(f"{Colors.GREEN}{i}. {link}{Colors.RESET}")


async def main():
    parser = argparse.ArgumentParser(
        description='F11 Video Link Extractor - Kaçak sitelerden video linklerini çıkartır'
    )
    parser.add_argument('url', nargs='?', help='İzlenecek URL')
    parser.add_argument('-t', '--timeout', default=30000, type=int, help='Timeout (ms)')
    
    args = parser.parse_args()
    
    url = args.url
    if not url:
        url = input(f"{Colors.CYAN}İzlemek istediğiniz URL: {Colors.RESET}").strip()
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    async with VideoLinkExtractor(url, timeout=args.timeout) as extractor:
        await extractor.extract()
        extractor.show_results()
    
    # Kullanıcı girişini bekle
    print(f"\n{Colors.CYAN}Videoyu manuel oynatmak için Enter'e basın...{Colors.RESET}")
    await asyncio.to_thread(input)
    print(f"{Colors.YELLOW}Kapatılıyor...{Colors.RESET}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}İptal edildi.{Colors.RESET}")
        sys.exit(0)
