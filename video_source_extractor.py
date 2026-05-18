import asyncio
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Response, WebSocket
import json


class Colors:
    """ANSI renk kodları"""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class PageType(Enum):
    """Sayfa türleri"""
    MAIN_PAGE = "main_page"
    POP_UNDER = "pop_under"


@dataclass
class NetworkRequest:
    """Ağ isteği modeli"""
    url: str
    method: str
    resource_type: str
    status: Optional[int] = None
    page_type: PageType = PageType.MAIN_PAGE
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_video_source: bool = False
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Sonuç modeli"""
    main_page_requests: List[NetworkRequest] = field(default_factory=list)
    pop_under_requests: List[NetworkRequest] = field(default_factory=list)
    video_sources: List[str] = field(default_factory=list)
    websocket_connections: List[str] = field(default_factory=list)


class VideoSourceExtractor:
    """Video kaynağı çıkaran ana sınıf"""
    
    # Video kaynağı anahtar kelimeleri ve dosya uzantıları
    VIDEO_EXTENSIONS = {".m3u8", ".mp4", ".ts", ".mkv", ".avi", ".mov"}
    VIDEO_KEYWORDS = {
        "video", "stream", "embed", "vidsrc", "player",
        "hls", "dash", "m3u8", "mp4", "chunk", "segment"
    }
    
    def __init__(self, url: str, headless: bool = True, timeout: int = 30000):
        """
        Başlatıcı method
        
        Args:
            url: Taranacak web sayfası URL'si
            headless: Tarayıcı başlığını gizle
            timeout: İstek timeout süresi (ms)
        """
        self.url = url
        self.headless = headless
        self.timeout = timeout
        self.result = ExtractionResult()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.main_page: Optional[Page] = None
        self.popup_pages: List[Page] = []
        
    async def setup(self) -> None:
        """Tarayıcı ve sayfa yapılandırması"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=self.headless)
        
        # Context ile başlat (pop-under izlemesi için gerekli)
        self.context = await self.browser.new_context()
        
        # Pop-under/popup sayfalarını otomatik olarak kapat
        self.context.on("page", self._handle_popup_page)
        
        self.main_page = await self.context.new_page()
        await self.main_page.set_default_timeout(self.timeout)
        
        # Ana sayfa için event listener'ları bağla
        await self._attach_page_listeners(self.main_page, PageType.MAIN_PAGE)
    
    async def _handle_popup_page(self, popup_page: Page) -> None:
        """
        Pop-under/popup sayfa açıldığında tetiklenen handler
        
        Args:
            popup_page: Yeni açılan popup sayfası
        """
        page_url = popup_page.url if popup_page else "unknown"
        print(
            f"{Colors.MAGENTA}{Colors.BOLD}"
            f"⚠️  POP-UNDER DETECTED: {page_url}"
            f"{Colors.RESET}"
        )
        
        self.popup_pages.append(popup_page)
        
        # Popup'a da listener'ları bağla (kapatmadan önce trafiği yakala)
        await self._attach_page_listeners(popup_page, PageType.POP_UNDER)
        
        # 2 saniye bekle (trafiği yakala), sonra kapat
        await asyncio.sleep(2)
        await popup_page.close()
        print(
            f"{Colors.GREEN}{Colors.BOLD}"
            f"✓ Pop-under kapatıldı"
            f"{Colors.RESET}"
        )
    
    async def _attach_page_listeners(
        self,
        page: Page,
        page_type: PageType
    ) -> None:
        """
        Sayfaya network event listener'larını bağla
        
        Args:
            page: Listener'ların bağlanacağı sayfa
            page_type: Sayfa türü (main veya pop_under)
        """
        page.on("request", lambda req: asyncio.create_task(
            self._on_request(req, page_type)
        ))
        page.on("response", lambda res: asyncio.create_task(
            self._on_response(res, page_type)
        ))
        page.on("websocket", lambda ws: asyncio.create_task(
            self._on_websocket(ws, page_type)
        ))
    
    async def _on_request(
        self,
        request: Any,
        page_type: PageType
    ) -> None:
        """
        İstek event handler'ı
        
        Args:
            request: Istek nesnesi
            page_type: Sayfa türü
        """
        try:
            network_req = NetworkRequest(
                url=request.url,
                method=request.method,
                resource_type=request.resource_type,
                page_type=page_type,
                headers=dict(request.headers)
            )
            
            # İsteği sonuçlara ekle
            if page_type == PageType.MAIN_PAGE:
                self.result.main_page_requests.append(network_req)
            else:
                self.result.pop_under_requests.append(network_req)
                
        except Exception as e:
            print(f"{Colors.RED}❌ Request parsing error: {e}{Colors.RESET}")
    
    async def _on_response(
        self,
        response: Response,
        page_type: PageType
    ) -> None:
        """
        Response event handler'ı - Video linklerini yakala
        
        Args:
            response: Response nesnesi
            page_type: Sayfa türü
        """
        try:
            url = response.url
            status = response.status
            
            # Video kaynağı kontrol et
            if self._is_video_source(url):
                self.result.video_sources.append(url)
                
                print(
                    f"\n{Colors.RED}{Colors.BOLD}"
                    f"{'=' * 70}"
                    f"\n🎬 ASIL VİDEO LİNKİ BULUNDU [{page_type.value}]"
                    f"\n{'=' * 70}{Colors.RESET}"
                )
                print(f"{Colors.CYAN}URL: {url}{Colors.RESET}")
                print(f"{Colors.YELLOW}Status: {status}{Colors.RESET}")
                print(f"{Colors.BOLD}Content-Type: {response.headers.get('content-type', 'N/A')}{Colors.RESET}")
                print(
                    f"{Colors.RED}{Colors.BOLD}"
                    f"{'=' * 70}\n{Colors.RESET}"
                )
                
        except Exception as e:
            print(f"{Colors.RED}❌ Response parsing error: {e}{Colors.RESET}")
    
    async def _on_websocket(
        self,
        websocket: WebSocket,
        page_type: PageType
    ) -> None:
        """
        WebSocket bağlantısı event handler'ı
        
        Args:
            websocket: WebSocket nesnesi
            page_type: Sayfa türü
        """
        try:
            ws_url = websocket.url
            self.result.websocket_connections.append(ws_url)
            print(
                f"{Colors.CYAN}🔌 WebSocket [{page_type.value}]: {ws_url}{Colors.RESET}"
            )
        except Exception as e:
            print(f"{Colors.RED}❌ WebSocket error: {e}{Colors.RESET}")
    
    def _is_video_source(self, url: str) -> bool:
        """
        URL'nin video kaynağı olup olmadığını kontrol et
        
        Args:
            url: Kontrol edilecek URL
            
        Returns:
            Video kaynağıysa True
        """
        url_lower = url.lower()
        
        # Dosya uzantısı kontrol et
        if any(url_lower.endswith(ext) for ext in self.VIDEO_EXTENSIONS):
            return True
        
        # Anahtar kelime kontrol et
        if any(keyword in url_lower for keyword in self.VIDEO_KEYWORDS):
            return True
        
        return False
    
    async def _auto_click_video_player(self) -> None:
        """
        Video oynatıcı alanına otomatik tıklama simülasyonu
        Reklam katmanlarını geçmek için 2-3 kez tıkla
        """
        if not self.main_page:
            return
        
        print(
            f"{Colors.YELLOW}{Colors.BOLD}"
            f"🖱️  Reklam katmanlarını geçmek için otomatik tıklama başlıyor..."
            f"{Colors.RESET}"
        )
        
        try:
            # Sayfanın merkezine 2 kez tıkla
            viewport = self.main_page.viewportSize
            if viewport:
                center_x = viewport["width"] // 2
                center_y = viewport["height"] // 2
                
                for i in range(3):
                    await self.main_page.mouse.click(center_x, center_y)
                    await asyncio.sleep(1)
                    print(f"{Colors.GREEN}✓ Tıklama #{i + 1}{Colors.RESET}")
                    
        except Exception as e:
            print(f"{Colors.RED}❌ Auto-click error: {e}{Colors.RESET}")
    
    async def extract(self, wait_for_input: bool = True) -> ExtractionResult:
        """
        Video kaynaklarını çıkart
        
        Args:
            wait_for_input: Kullanıcı girdisi beklenip beklenmeyeceği
            
        Returns:
            Çıkarılan sonuçlar
        """
        try:
            # Sayfayı yükle
            print(f"{Colors.CYAN}{Colors.BOLD}📄 Sayfa yükleniyor: {self.url}{Colors.RESET}")
            await self.main_page.goto(self.url, wait_until="domcontentloaded")
            
            # Sayfanın tam yüklenmesi için bekleme
            await asyncio.sleep(3)
            
            # Otomatik tıklama (reklam katmanlarını geçmek için)
            await self._auto_click_video_player()
            
            # Pop-under ve reklam akışına izin vermek için bekleme
            print(
                f"{Colors.YELLOW}{Colors.BOLD}"
                f"⏱️  Ağ trafiği izleniyor (30 saniye)...{Colors.RESET}"
            )
            
            if wait_for_input:
                # Kullanıcı girdisi bekle
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: input(
                        f"{Colors.YELLOW}\n"
                        f"Video oynatmayı başlat veya reklamlar yüklenene kadar bekleme yapın.\n"
                        f"Bitirme için Enter'a basın...{Colors.RESET}\n"
                    )
                )
            else:
                # Otomatik bekleme
                await asyncio.sleep(30)
            
            return self.result
            
        except Exception as e:
            print(f"{Colors.RED}{Colors.BOLD}❌ Extraction error: {e}{Colors.RESET}")
            return self.result
    
    def print_results(self) -> None:
        """Sonuçları tablo formatında yazdır"""
        print(
            f"\n{Colors.BOLD}{Colors.CYAN}"
            f"{'=' * 80}\n"
            f"📊 ÇIKARILAN NETWORK TRAFİĞİ\n"
            f"{'=' * 80}{Colors.RESET}\n"
        )
        
        # Video kaynakları
        print(f"{Colors.RED}{Colors.BOLD}🎬 ASIL VİDEO KAYNAKLARI:{Colors.RESET}")
        if self.result.video_sources:
            for idx, video_url in enumerate(self.result.video_sources, 1):
                print(f"{Colors.GREEN}{idx}. {video_url}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}⚠️  Video kaynağı bulunamadı{Colors.RESET}")
        
        # Ana sayfa istekleri
        print(
            f"\n{Colors.CYAN}{Colors.BOLD}"
            f"📌 ANA SAYFA İSTEKLERİ ({len(self.result.main_page_requests)}){Colors.RESET}"
        )
        self._print_requests_table(self.result.main_page_requests)
        
        # Pop-under istekleri
        if self.result.pop_under_requests:
            print(
                f"\n{Colors.MAGENTA}{Colors.BOLD}"
                f"⚠️  POP-UNDER İSTEKLERİ ({len(self.result.pop_under_requests)}){Colors.RESET}"
            )
            self._print_requests_table(self.result.pop_under_requests)
        
        # WebSocket bağlantıları
        if self.result.websocket_connections:
            print(
                f"\n{Colors.CYAN}{Colors.BOLD}"
                f"🔌 WEBSOCKET BAĞLANTILARI ({len(self.result.websocket_connections)}){Colors.RESET}"
            )
            for ws_url in self.result.websocket_connections:
                print(f"{Colors.WHITE}{ws_url}{Colors.RESET}")
        
        print(f"\n{Colors.CYAN}{'=' * 80}{Colors.RESET}\n")
    
    def _print_requests_table(self, requests: List[NetworkRequest]) -> None:
        """
        İstekleri tablo olarak yazdır
        
        Args:
            requests: Yazdırılacak istekler
        """
        if not requests:
            return
        
        # Tablo başlığı
        headers = ["#", "Metod", "Türü", "URL"]
        col_widths = [3, 8, 12, 55]
        
        # Başlık satırı
        header_row = " | ".join(
            h.ljust(w) for h, w in zip(headers, col_widths)
        )
        print(f"{Colors.BOLD}{Colors.WHITE}{header_row}{Colors.RESET}")
        print("-" * sum(col_widths) + "---")
        
        # Veri satırları
        for idx, req in enumerate(requests[:20], 1):  # İlk 20 isteği göster
            url_short = req.url[:55] if len(req.url) > 55 else req.url
            row = f"{str(idx).ljust(3)} | {req.method.ljust(8)} | {req.resource_type.ljust(12)} | {url_short}"
            print(f"{Colors.WHITE}{row}{Colors.RESET}")
        
        if len(requests) > 20:
            print(f"{Colors.YELLOW}... ve {len(requests) - 20} istek daha{Colors.RESET}")
    
    async def cleanup(self) -> None:
        """Kaynakları temizle"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()


async def main():
    """Ana fonksiyon"""
    # Test URL'i (örnek kaçak film sitesi - gerçek URL yerine kullan)
    target_url = "https://example.com/video"  # Buraya hedef URL'i gir
    
    # Kullanıcıdan URL girmesini iste
    print(f"{Colors.CYAN}{Colors.BOLD}🎬 Video Kaynağı Çıkaran Tool{Colors.RESET}\n")
    user_url = input(f"{Colors.YELLOW}Taranacak URL'yi gir (Enter ile varsayılanı kullan): {Colors.RESET}").strip()
    
    if user_url:
        target_url = user_url
    
    # Çıkarıcı oluştur ve çalıştır
    extractor = VideoSourceExtractor(target_url, headless=False)
    
    try:
        await extractor.setup()
        result = await extractor.extract(wait_for_input=True)
        extractor.print_results()
        
    finally:
        await extractor.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
