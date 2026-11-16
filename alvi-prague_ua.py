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
# Discount markup (seen 2026-10-26, HALLOWEEN promotion), sticky bar and JSON-LD hold the special price:
#       <div class="product-hero__prices">
#         <p class="product-hero__price product-hero__price--special">5 485 500 грн</p>
#         <p class="product-hero__price product-hero__price--old"><s>6 095 000 грн</s></p>
#       </div>
#     </div>
#     <div class="promotion-countdown promotion-countdown--product" ...> ... (timer and sticker, no prices) </div>
#
# Discount markup (seen 2026-11-16, BLACK FRIDAY promotion): wrap gets a modifier and the sticker moves inside it:
#     <div class="product-hero__price-wrap product-hero__price-wrap--promotion">
#       <div class="product-hero__prices"> ... special + old, as above ... </div>
#       <a class="promotion-sticker promotion-sticker--product" href=".../promotion"><img ...></a>
#     </div>
#     <div class="promotion-countdown promotion-countdown--product" ...> ... (timer, no prices) </div>
#
# Products that can't be bought (since 2026-10-16): no price-wrap and no sticky bar at all, the price is only in
# JSON-LD with "availability": "https://schema.org/OutOfStock" (or no offers at all -> price 0, as before).
#
# Anything else raises PriceMarkupChanged: the parser must be revised by hand.
# ---------------------------------------------------------------------------------------------------------------------

PRICE_RE = re.compile(r'\d{1,3}(?: \d{3})* грн')
LD_PRICE_RE = re.compile(r'\d+(?:\.\d{1,2})?')
PRICE_HINT_RE = re.compile(r'price|discount|sale|special|promo|percent|(?<![a-z])old', re.I)

REGULAR_PRICE_CLASSES = {'product-hero__price'}
SPECIAL_PRICE_CLASSES = {'product-hero__price', 'product-hero__price--special'}
OLD_PRICE_CLASSES = {'product-hero__price', 'product-hero__price--old'}
WRAP_CLASSES = {'product-hero__price-wrap'}
PROMOTION_WRAP_CLASSES = {'product-hero__price-wrap', 'product-hero__price-wrap--promotion'}
PROMOTION_STICKER_CLASSES = {'promotion-sticker', 'promotion-sticker--product'}
KNOWN_HERO_PRICE_CLASSES = {
    'product-hero__price-wrap',
    'product-hero__price-wrap--promotion',
    'product-hero__prices',
    'product-hero__price',
    'product-hero__price--special',
    'product-hero__price--old',
}
# Promotion timer and sticker next to the discounted price
PROMOTION_CLASS_RE = re.compile(r'promotion-(?:countdown|sticker)(?:__[a-z]+)?(?:--[a-z]+)?')
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

    # 1. Price block: exactly one wrap containing exactly one prices block,
    #    promotion wrap may also hold one promotion sticker after it
    wraps = hero.find_all(class_='product-hero__price-wrap')
    blocks = hero.find_all(class_='product-hero__prices')
    if not wraps and not blocks:
        return check_hidden_price(soup, hero, ld_product)
    if len(wraps) != 1 or len(blocks) != 1:
        raise PriceMarkupChanged(f'Price block structure changed: {str(wraps[0] if wraps else hero)[:500]}')
    wrap_classes = set(wraps[0].get('class', []))
    wrap_children = element_children(wraps[0])
    if wrap_classes == WRAP_CLASSES:
        promotion_wrap = False
        known_wrap_children = wrap_children == [blocks[0]]
    elif wrap_classes == PROMOTION_WRAP_CLASSES:
        promotion_wrap = True
        known_wrap_children = wrap_children[:1] == [blocks[0]] and len(wrap_children) <= 2 and all(
            t.name == 'a' and set(t.get('class', [])) == PROMOTION_STICKER_CLASSES for t in wrap_children[1:]
        )
    else:
        known_wrap_children = False
    if not known_wrap_children:
        raise PriceMarkupChanged(f'Price block structure changed: {str(wraps[0])[:500]}')

    # 2. Inside the prices block: a regular price alone, or a discount: special price + old price in <s>
    price_tags = {}
    for p in element_children(blocks[0]):
        classes = set(p.get('class', []))
        inner_tags = [t.name for t in p.find_all(True)]
        if p.name == 'p' and classes == REGULAR_PRICE_CLASSES and not inner_tags:
            kind = 'regular'
        elif p.name == 'p' and classes == SPECIAL_PRICE_CLASSES and not inner_tags:
            kind = 'special'
        elif p.name == 'p' and classes == OLD_PRICE_CLASSES and inner_tags == ['s']:
            kind = 'old'
        else:
            raise PriceMarkupChanged(f'Unknown element in price block: {str(p)[:300]}')
        if kind in price_tags:
            raise PriceMarkupChanged(f'Two {kind} prices in price block: {str(blocks[0])[:300]}')
        price_tags[kind] = p

    if set(price_tags) == {'regular'}:
        newprice, oldprice = parse_price_text(price_tags['regular']), None
    elif set(price_tags) == {'special', 'old'}:
        newprice, oldprice = parse_price_text(price_tags['special']), parse_price_text(price_tags['old'])
        if oldprice <= newprice:
            raise PriceMarkupChanged(f'Old price {oldprice} is not greater than special price {newprice}')
    else:
        raise PriceMarkupChanged(f'Unexpected set of prices {sorted(price_tags)}: {str(blocks[0])[:300]}')
    if promotion_wrap and oldprice is None:
        raise PriceMarkupChanged(f'Promotion price wrap without discounted price: {str(wraps[0])[:300]}')

    # 3. Discount signs elsewhere in the product hero
    check_no_discount_signs(hero, blocks[0], discounted=oldprice is not None)

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
    check_no_discount_signs(hero, None, discounted=False)

    offers = ld_product.get('offers')
    if offers is None:  # products without any price, written with 0 as before
        return 0, None
    if offers.get('availability') not in NOT_FOR_SALE_AVAILABILITY:
        raise PriceMarkupChanged(
            f'No price block on the page, but JSON-LD availability is {offers.get("availability")!r}'
        )
    return get_ld_price(ld_product), None


def check_no_discount_signs(hero: Tag, price_block: Optional[Tag], discounted: bool) -> None:
    """
    Raises on strikethrough, price/sale/discount classes or our known price classes outside the price block.
    Promotion timer / sticker is allowed only next to a discounted price and must not contain prices.
    """
    allowed = set() if price_block is None else {id(price_block), id(price_block.parent)}
    if price_block is not None:
        allowed |= {id(t) for t in price_block.find_all(True)}
    for tag in hero.find_all(True):
        classes = tag.get('class', [])
        if tag.name in ('s', 'del', 'strike') and id(tag) not in allowed:
            raise PriceMarkupChanged(f'Strikethrough outside price block: {str(tag)[:300]}')
        if id(tag) not in allowed and set(classes) & KNOWN_HERO_PRICE_CLASSES:
            raise PriceMarkupChanged(f'Price element outside price block: {str(tag)[:300]}')
        if any(PROMOTION_CLASS_RE.fullmatch(c) for c in classes):
            if not discounted:
                raise PriceMarkupChanged(f'Promotion block without discounted price: {str(tag)[:300]}')
            if 'грн' in tag.get_text():
                raise PriceMarkupChanged(f'Price inside promotion block: {str(tag)[:300]}')
        if unknown := [
            c for c in classes
            if PRICE_HINT_RE.search(c) and c not in KNOWN_HERO_PRICE_CLASSES and not PROMOTION_CLASS_RE.fullmatch(c)
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
