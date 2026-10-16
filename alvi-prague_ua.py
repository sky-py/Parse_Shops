import json
import re
from decimal import Decimal, InvalidOperation
from typing import Optional
from bs4 import BeautifulSoup, Tag
from messengers import send_service_tg_message
from parser import Parser, Product


main_lang = 'ua'
lang = {
    'ua': {'site': 'https://alvi-prague.ua/uk', 'in_stock': 'Є в наявності'},
    'ru': {'site': 'https://alvi-prague.ua/', 'in_stock': 'Есть в наличии'},
}


def translate(element):
    return lang[main_lang][element]


# ---------------------------------------------------------------------------------------------------------------------
# Safety checks for price markup.
#
# Current markup (2026-10):
#   <section class="product-hero"> ...
#     <div class="product-hero__price-wrap">
#       <div class="product-hero__prices">
#         <p class="product-hero__price">1 104 299 грн</p>
#       </div>
#     </div>
#   <span class="sticky-buy-bar__price">1 104 299 грн</span>
#   <script type="application/ld+json">{"@type":"Product", "model": ..., "offers":{"@type":"Offer","price":"1104299.00",...}}
#
# Predicted discount markup (site CSS already has .product-hero__price--old and .product-hero__price--old s):
#         <p class="product-hero__price">999 999 грн</p>
#         <p class="product-hero__price product-hero__price--old"><s>1 104 299 грн</s></p>
#
# Products that can't be bought (since 2026-10-16): no price-wrap and no sticky bar at all, the price is only in
# JSON-LD with "availability": "https://schema.org/OutOfStock" (or no offers at all -> price 0, as before).
#
# Anything else raises PriceMarkupChanged: the parser must be revised by hand.
# ---------------------------------------------------------------------------------------------------------------------

PRICE_RE = re.compile(r'\d{1,3}(?: \d{3})* грн')
LD_PRICE_RE = re.compile(r'\d+(?:\.\d{1,2})?')
PRICE_HINT_RE = re.compile(r'price|discount|sale|special|promo|percent|(?<![a-z])old', re.I)

NEW_PRICE_CLASSES = {'product-hero__price'}
OLD_PRICE_CLASSES = [{'product-hero__price', 'product-hero__price--old'}, {'product-hero__price--old'}]
KNOWN_HERO_PRICE_CLASSES = {
    'product-hero__price-wrap',
    'product-hero__prices',
    'product-hero__price',
    'product-hero__price--old',
}
KNOWN_OFFER_KEYS = {'@type', 'url', 'priceCurrency', 'price', 'availability', 'itemCondition', 'seller'}
IN_STOCK_TEXTS = {lang['ua']['in_stock'], lang['ru']['in_stock']}
NOT_FOR_SALE_AVAILABILITY = {
    'https://schema.org/OutOfStock',
    'https://schema.org/Discontinued',
    'https://schema.org/SoldOut',
}


class PriceMarkupChanged(Exception):
    pass


def parse_price_text(tag: Tag) -> int:
    """'1 104 299 грн' -> 1104299. Anything else ('від ...', two prices in one tag, other currency) raises."""
    text = re.sub(r'\s+', ' ', tag.get_text(' ', strip=True).replace('\xa0', ' ').replace(' ', ' '))
    if not PRICE_RE.fullmatch(text):
        raise PriceMarkupChanged(f'Unexpected price text {text!r} in {tag.name}.{".".join(tag.get("class", []))}')
    return int(text.replace(' грн', '').replace(' ', ''))


def element_children(tag: Tag) -> list[Tag]:
    """Child tags of an element. Raises if the element also holds bare text (e.g. a price outside of a tag)."""
    loose_text = [s.strip() for s in tag.find_all(string=True, recursive=False) if s.strip()]
    if loose_text:
        raise PriceMarkupChanged(f'Unexpected text {loose_text} inside {".".join(tag.get("class", []))}')
    return tag.find_all(True, recursive=False)


def get_ld_product(soup: BeautifulSoup) -> dict:
    """Returns the JSON-LD Product object, checking that its offer has the known shape."""
    products = []
    for script in soup.find_all('script', {'type': 'application/ld+json'}):
        try:
            data = json.loads(script.string)
        except (TypeError, ValueError) as e:
            raise PriceMarkupChanged(f'JSON-LD is not valid JSON: {e}')
        for item in data if isinstance(data, list) else data.get('@graph', [data]):
            if isinstance(item, dict) and item.get('@type') == 'Product':
                products.append(item)
    if len(products) != 1:
        raise PriceMarkupChanged(f'Expected 1 JSON-LD Product, found {len(products)}')
    ld_product = products[0]

    if not isinstance(ld_product.get('model'), str) or not ld_product['model'].strip():
        raise PriceMarkupChanged(f'JSON-LD model (product code) is missing: {ld_product.get("model")!r}')

    offers = ld_product.get('offers')
    if offers is None:  # products without price ('0 грн' on the page) have no offers, checked in check_price_markup
        return ld_product
    # A list of offers, AggregateOffer or new keys (priceSpecification, priceValidUntil, highPrice, ...)
    # usually mean the site started to describe discounts / variants in JSON-LD
    if not isinstance(offers, dict) or offers.get('@type') != 'Offer':
        raise PriceMarkupChanged(f'JSON-LD offers changed: {str(offers)[:300]}')
    if unknown_keys := set(offers) - KNOWN_OFFER_KEYS:
        raise PriceMarkupChanged(f'New keys in JSON-LD offers: {sorted(unknown_keys)}')
    if offers.get('priceCurrency') != 'UAH':
        raise PriceMarkupChanged(f'JSON-LD currency changed: {offers.get("priceCurrency")!r}')
    if not LD_PRICE_RE.fullmatch(str(offers.get('price'))):
        raise PriceMarkupChanged(f'JSON-LD price has unexpected format: {offers.get("price")!r}')
    return ld_product


def check_price_markup(soup: BeautifulSoup, ld_product: dict) -> tuple[int, Optional[int]]:
    """Returns (price, old_price) and raises PriceMarkupChanged on any markup that differs from the known one."""
    hero = soup.find('section', {'class': 'product-hero'})
    if hero is None:
        raise PriceMarkupChanged('section.product-hero not found')

    # 1. Price block: exactly one wrap containing exactly one prices block and nothing else
    wraps = hero.find_all(class_='product-hero__price-wrap')
    blocks = hero.find_all(class_='product-hero__prices')
    if not wraps and not blocks:
        return check_hidden_price(soup, hero, ld_product)
    if len(wraps) != 1 or len(blocks) != 1 or element_children(wraps[0]) != [blocks[0]]:
        raise PriceMarkupChanged(f'Price block structure changed: {str(wraps[0] if wraps else hero)[:500]}')

    # 2. Inside the prices block: one current price and optionally one old price in the predicted form
    new_tags, old_tags = [], []
    for p in element_children(blocks[0]):
        classes = set(p.get('class', []))
        inner_tags = [t.name for t in p.find_all(True)]
        if p.name == 'p' and classes == NEW_PRICE_CLASSES and not inner_tags:
            new_tags.append(p)
        elif p.name == 'p' and classes in OLD_PRICE_CLASSES and inner_tags in ([], ['s'], ['del']):
            old_tags.append(p)
        else:
            raise PriceMarkupChanged(f'Unknown element in price block: {str(p)[:300]}')
    if len(new_tags) != 1 or len(old_tags) > 1:
        raise PriceMarkupChanged(f'Expected 1 price and at most 1 old price, found {len(new_tags)} and {len(old_tags)}')

    newprice = parse_price_text(new_tags[0])
    oldprice = parse_price_text(old_tags[0]) if old_tags else None
    if oldprice is not None and oldprice <= newprice:
        raise PriceMarkupChanged(f'Old price {oldprice} is not greater than price {newprice}')

    # 3. Discount signs elsewhere in the product hero
    check_no_discount_signs(hero, blocks[0])

    # 4. Sticky buy bar repeats the current price (no bar for products that can't be bought)
    sticky = soup.find_all(class_='sticky-buy-bar__price')
    if len(sticky) > 1 or (sticky and (sticky[0].find(True) is not None or parse_price_text(sticky[0]) != newprice)):
        raise PriceMarkupChanged(f'Sticky bar price differs: {[str(t)[:200] for t in sticky]}')

    # 5. JSON-LD price must be the current price. No offers is known only for products with '0 грн'
    if ld_product.get('offers') is None:
        if newprice != 0 or oldprice is not None:
            raise PriceMarkupChanged(f'JSON-LD has no offers, but page price is {newprice} / old {oldprice}')
        return newprice, oldprice
    ld_price = get_ld_price(ld_product)
    if ld_price != newprice:
        raise PriceMarkupChanged(f'JSON-LD price {ld_price} differs from page price {newprice}')

    return newprice, oldprice


def check_hidden_price(soup: BeautifulSoup, hero: Tag, ld_product: dict) -> tuple[int, None]:
    """No price block on the page: allowed only for products that can't be bought, price is taken from JSON-LD."""
    stock = hero.find(class_='product-hero__stock')
    stock_text = stock.get_text(strip=True) if stock else None
    if stock_text is None or stock_text in IN_STOCK_TEXTS:
        raise PriceMarkupChanged(f'No price block on the page, stock: {stock_text!r}')
    if soup.find(class_='sticky-buy-bar__price'):
        raise PriceMarkupChanged('No price block on the page, but sticky bar has a price')
    check_no_discount_signs(hero, None)

    offers = ld_product.get('offers')
    if offers is None:  # products without any price, written with 0 as before
        return 0, None
    if offers.get('availability') not in NOT_FOR_SALE_AVAILABILITY:
        raise PriceMarkupChanged(
            f'No price block on the page, but JSON-LD availability is {offers.get("availability")!r}'
        )
    return get_ld_price(ld_product), None


def check_no_discount_signs(hero: Tag, price_block: Optional[Tag]) -> None:
    """Raises on strikethrough, price/sale/discount classes or our known price classes outside the price block."""
    allowed = set() if price_block is None else {id(price_block), id(price_block.parent)}
    if price_block is not None:
        allowed |= {id(t) for t in price_block.find_all(True)}
    for tag in hero.find_all(True):
        if tag.name in ('s', 'del', 'strike') and id(tag) not in allowed:
            raise PriceMarkupChanged(f'Strikethrough outside price block: {str(tag)[:300]}')
        if id(tag) not in allowed and set(tag.get('class', [])) & KNOWN_HERO_PRICE_CLASSES:
            raise PriceMarkupChanged(f'Price element outside price block: {str(tag)[:300]}')
        if unknown := [
            c for c in tag.get('class', []) if PRICE_HINT_RE.search(c) and c not in KNOWN_HERO_PRICE_CLASSES
        ]:
            raise PriceMarkupChanged(f'Unknown price-like classes {unknown}: {str(tag)[:300]}')


def get_ld_price(ld_product: dict) -> int:
    try:
        ld_price = Decimal(ld_product['offers']['price'])
    except InvalidOperation:
        raise PriceMarkupChanged(f'JSON-LD price is not a number: {ld_product["offers"]["price"]!r}')
    if ld_price != int(ld_price):
        raise PriceMarkupChanged(f'JSON-LD price has kopecks: {ld_price}')
    return int(ld_price)


class Site(Parser):
    price_file = 'alvi-prague_ua.xlsx'
    site = 'https://alvi-prague.ua/uk'
    max_products_per_page = '?limit=100'
    excluded_links = ['#', '/promotion/']
    use_discount = False

    art_clmn = 1
    name_clmn = 2
    price_clmn = 3
    oldprice_clmn = 4
    available_clmn = 5
    link_clmn = 6
    group_clmn = 7

    async def get_categories_links(self, link: str) -> list[str]:
        categories_links = []
        soup = await self.get_soup(link)
        for a in soup.select('li.mega-menu__column-title > a'):
            categories_links.append(a['href'])
        return categories_links

    async def get_products_links(self, category_link: str) -> list[str]:
        products_links = []
        soup = await self.get_soup(category_link + self.max_products_per_page)
        for a in soup.find_all('a', {'class': 'featured-product-card__title'}):
            products_links.append(a['href'])
        return products_links

    async def get_product_info(self, product_link: str) -> list[Product]:
        soup = await self.get_soup(product_link)
        name = soup.find('h1', {'class': 'product-hero__title'}).get_text(strip=True)

        stock_text = soup.find('span', {'class': 'product-hero__stock'}).get_text(strip=True)
        if stock_text in (lang['ua']['in_stock'], lang['ru']['in_stock']):  # site mixes languages here
            available = '+'
        else:
            available = '-'

        # Markup change stops the whole run: one message instead of an error per product
        # and no xlsx saved with prices of unknown origin
        try:
            ld_product = get_ld_product(soup)
            newprice, oldprice = check_price_markup(soup, ld_product)
        except PriceMarkupChanged as e:
            send_service_tg_message(f'Изменилась разметка цены {product_link}\n{e}\n{__file__}\n')
            exit(1)

        art = ld_product['model'].strip()

        return [
            Product(
                name=name,
                art=art,
                price=newprice,
                old_price=oldprice,
                available=available,
                link=product_link,
                variant=None,
            )
        ]


Site().parse()
