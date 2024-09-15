# Description
This is a parser for different shop sites.
Usually shop site has product categories and each category has multiple products in it.
If you want to implement your own parser, you need to follow these simple steps:
1. Create a file, import `Parser` and `Product` classes and inherit your own class `Parser`.
2. Implement 3 methods: `get_categories_links`, `get_products_links`, and `get_product_info` which are responsible for getting categories links, getting all product links in a particular category, and getting product properties on a particular product page correspondingly.

For example, in the simplest case, your own parser can look like this:

```python
from parser import Parser, Product


class Site(Parser):
    price_file = 'results.xlsx'
    site = 'https://shop-site.com'

    async def get_categories_links(self, link: str) -> list[str]:
        soup = await self.get_soup(link)
        return [a['href'] for a in soup.find_all("a", {"class": "menu-items"})]

    async def get_products_links(self, category_link: str) -> list[str]:
        soup = await self.get_soup(category_link)
        return [div.a['href'] for div in soup.find_all("div", {"class": "product-card"})]

    async def get_product_info(self, product_link: str) -> list[
        Product]:  # there can be products with multiple variants on the page
        soup = await self.get_soup(product_link)
        name = soup.find("h1").string
        available = '+' if soup.find("span", {"class": "stock-text"}).string == 'in_stock' else '-'
        price = int(soup.find("div", {"class": "mobile-price"}).string)
        old_price = soup.find("div", {"class": "old-price"}).string
        art = soup.find("li", {"class": "sku"}).string
        return [Product(name=name, art=art, price=price, old_price=old_price,
                        available=available, link=product_link, variant=None)]


Site().parse()
```

# How to install
```bash
pip install -r requirements.txt
playwright install  # if you need dynamically load javascript pages
```

# Additional parameters
There are banch of parameters in `Parser` class, that you can redefine at your subclass (for more info see `parser.py` file):
```python
number_of_workers = 3  # Number of concurrent asynchronous workers
worker_timeout = 1  # Timeout in seconds for each worker
worker_attempts = 2  # Number of attempts to fetch a page before giving up

use_discount = True  # Whether to consider supplier's discount in calculations
max_products_per_page = ''  # String to append to category URLs to maximize product output

excluded_links = []  # List of product links to exclude from parsing
excluded_links_parts = []  # List of URL fragments to exclude links containing them
excluded_categories_links_parts = []  # List of URL fragments to exclude categories containing them

# User agent and extra headers settings ....

# Proxy settings ...

# Column numbers for storing data in the Excel file ...

# Additional configuration options
render_javascript = False  # Enable JavaScript rendering
headless = True  # Run the browser in headless mode. False for clouflare protection
use_connection_pool = True  # Reuse existing network connections if True, create new ones otherwise
use_dalayed_availability = True  # Delay marking products as unavailable until multiple checks
compared_product_field = 'art'  # Field used as primary key to identify products (art or name)
max_unavailable_count = 4  # Maximum number of checks before marking a product as unavailable
```