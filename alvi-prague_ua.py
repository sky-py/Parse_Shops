import re
from parser import Parser, Product
from messengers import send_service_tg_message


main_lang = 'ua'
lang = {
    'ua': {
        'site': 'https://alvi-prague.ua/uk',
        'in_stock': 'Є в наявності',
        'kod': 'Код товару:'
    },
    'ru': {
        'site': 'https://alvi-prague.ua/',
        'in_stock': 'Есть в наличии',
        'kod': 'Код товара:'
    }
}


def translate(element):
    return lang[main_lang][element]


class Site(Parser):
    price_file = 'alvi-prague_ua.xlsx'
    site = 'https://alvi-prague.ua/uk'
    max_products_per_page = '?limit=100'
    excluded_links = ['#', '/promotion/']
    use_discount = False

    render_javascript = False
    number_of_workers = 1
    worker_timeout = 2

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
        for main_cat in soup.find_all("a", {"class": "toggle-desktop"}):
            podcat_links = main_cat.parent.find_all("li")
            for li in podcat_links:
                categories_links.append(li.a['href'])
        return categories_links

    async def get_products_links(self, category_link: str) -> list[str]:
        products_links = []
        soup = await self.get_soup(category_link + self.max_products_per_page)
        for div in soup.find_all("div", {"class": "name-product-card"}):
            products_links.append(div.a['href'])
        return products_links

    async def get_product_info(self, product_link: str) -> list[Product]:
        soup = await self.get_soup(product_link)
        name = soup.find("h1").string

        if soup.find("span", {"class": "stock-text"}).string == translate('in_stock'):   # status out-of-stock
            available = '+'
        else:
            available = '-'

        newprice, oldprice, newprice2, oldprice2 = None, None, None, None

        price_tag = soup.find("div", {"class": "mobile-price"})

        try:
            newprice = self.get_price(price_tag.string)
        except:
            pass

        try:
            newprice = self.get_price(price_tag.b.string)
        except:
            pass

        try:
            oldprice = self.get_price(price_tag.span.string)
        except:
            pass

        price_tag = soup.find("h2", {"id": "alviprice"})
        if price_tag is not None:
            newprice2 = self.get_price(price_tag.string)
            try:
                oldprice2 = self.get_price(price_tag.parent.previous_sibling.previous_sibling.string)
            except:
                pass

        if newprice != newprice2 or oldprice != oldprice2:
            send_service_tg_message(f"Не равны цены извлечённые разными способами {__file__}\n")
            exit(1)

        art = soup.find("li", string=re.compile(translate('kod')))
        art = str(art.string).replace(translate('kod'), '').strip()

        return [Product(name=name,
                        art=art,
                        price=newprice,
                        old_price=oldprice,
                        available=available,
                        link=product_link,
                        variant=None)]


Site().parse()
