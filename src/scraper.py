import time
import logging
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

#configure logging to output to the terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_driver() -> webdriver.Chrome:
    """Configures and returns a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3") #suppress console clutter
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

def scrape_nintendo_base(url: str) -> List[Dict[str, Any]]:
    """Scrapes base game data from Nintendo using requests."""
    logger.info(f"Scraping Nintendo base data from: {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        games = soup.select("li.page-list-group-item[data-nsuid]")
        
        nintendo_list = []
        for g in games:
            name_tag = g.find("p", class_="page-title")
            name = name_tag.get_text(strip=True) if name_tag else None
            
            platform_tag = g.find("p", class_="page-data")
            platform = platform_tag.get_text(strip=True) if platform_tag else None
            
            link_tag = g.find("a", href=True)
            url_abs = "https://www.nintendo.co.uk" + link_tag["href"] if link_tag else None
            
            nsuid = g.get("data-nsuid")
            
            nintendo_list.append({
                "name": name,
                "platform": platform,
                "url": url_abs,
                "nsuid": nsuid,
                "price": None,
                "price_old": None,
                "badge": None,
                "date_range": None,
                "product_code": None,
                "out_of_stock": None,
                "source": "Nintendo"
            })
        logger.info(f"Successfully extracted {len(nintendo_list)} base Nintendo items.")
        return nintendo_list
    except Exception as e:
        logger.error(f"Failed to scrape Nintendo base data: {e}")
        return []

def scrape_nintendo_prices(url: str) -> List[Dict[str, Any]]:
    """Scrapes dynamic pricing data from Nintendo using Selenium."""
    logger.info(f"Scraping Nintendo pricing data via Selenium from: {url}")
    driver = setup_driver()
    price_list = []
    
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "p.price-small span[data-price]"))
        )
        time.sleep(4) #small delay
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        games = soup.select("li.page-list-group-item[data-nsuid]")
        
        for g in games:
            nsuid = g.get("data-nsuid")
            price_container = g.find("p", class_="price-small")
            
            price = None
            price_old = None
            
            if price_container:
                price_tag = price_container.find("span", {"data-price": True})
                if price_tag:
                    price = price_tag.get_text(strip=True).replace("*", "")
                    
                price_old_tag = price_container.find("span", class_="discount")
                if price_old_tag:
                    price_old = price_old_tag.get_text(strip=True)
                    
            price_list.append({
                "nsuid": nsuid,
                "price": price,
                "price_old": price_old
            })
        logger.info(f"Successfully extracted {len(price_list)} Nintendo price records.")
    except Exception as e:
        logger.error(f"Failed to scrape Nintendo prices: {e}")
    finally:
        driver.quit()
        
    return price_list

def scrape_playstation(url: str) -> List[Dict[str, Any]]:
    """Scrapes PlayStation games and prices using Selenium."""
    logger.info(f"Scraping PlayStation data via Selenium from: {url}")
    driver = setup_driver()
    ps_list = []
    
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".product-tile"))
        )
        time.sleep(2)
        
        #multipage navigation handling
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "button.desktop-pagination__button.right-chevron-blue")
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(4) # Polite delay
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".product-tile"))
            )
        except Exception:
            logger.warning("Next page button not found or clickable. Proceeding with current page.")
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        games = soup.select(".products-list-section .product-tile")
        
        for g in games:
            name_tag = g.select_one("p.product-card-details__name")
            name = name_tag.text.strip() if name_tag else None
            
            link_tag = g.select_one(".product-card-image .product-tile__full-width a")
            url_abs = link_tag["href"] if link_tag else None
            
            price_tags = g.select("div.product-card-details__price .text-product-price span.price-whole-text")
            price_now = price_tags[0].text.strip() if len(price_tags) >= 1 else None
            price_old = price_tags[1].text.strip() if len(price_tags) >= 2 else None
            
            badge_tag = g.select_one("div.badge .badge-label")
            badge = badge_tag.text.strip() if badge_tag else None
            
            date_tag = g.select_one("div.product-card_price .date-wrapper")
            date_range = date_tag.text.strip() if date_tag else None
            
            out_of_stock = g.select_one("p.out-stock-wrpr") is not None
            
            btn = g.select_one("button[data-product-code]")
            product_code = btn["data-product-code"] if btn else None
            
            ps_list.append({
                "name": name,
                "price": price_now,
                "price_old": price_old,
                "badge": badge,
                "date_range": date_range,
                "url": url_abs,
                "product_code": product_code,
                "out_of_stock": out_of_stock,
                "platform": "PS5",
                "nsuid": None,
                "source": "PlayStation"
            })
        logger.info(f"Successfully extracted {len(ps_list)} PlayStation items.")
    except Exception as e:
        logger.error(f"Failed to scrape PlayStation data: {e}")
    finally:
        driver.quit()
        
    return ps_list