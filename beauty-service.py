from parcer import Parcer, Product

main_lang = 'ua'
lang = {
    'ua': {
        'site': 'https://kosmetologia.com.ua/ua',
        'in_stock': 'На складі',
        'in_stock_2': 'В наявності',
        'kod': 'Код товару:',
        'discount': 'АКЦІЯ',
        'discount_2': 'уцінка'
    },
    'ru': {
        'site': 'https://kosmetologia.com.ua/',
        'in_stock': 'Есть в наличии',
        'in_stock_2': 'В наличии',
        'kod': 'Код товара:',
        'discount': 'АКЦИЯ',
        'discount_2': 'уценка',
    }
}


def translate(element):
    return lang[main_lang][element]


class Site(Parcer):
    compared_product_field = 'name'
    use_connection_pool = False
    price_file = 'Бьюти-Сервис.xlsx'
    site = 'https://kosmetologia.com.ua/ua'
    max_products_per_page = '?limit=500'
    excluded_links_parts = ['/seminary-dlya-kosmetologov', '/obuchayshchaya-kniga-vakuumnyi-massazh',]
    max_unavailable_count = 2

    async def get_categories_links(self, link: str) -> list[str]:
        categories_links = []
        soup = await self.get_soup(link)
        for main_cat in soup.find_all("li", {"class": "root root-dropdown"}):
            for li in main_cat.find_all("li"):
                cat_link = li.a['href']
                if not self.is_link_excluded_by_part(cat_link):
                    categories_links.append('https:' + cat_link)
        return categories_links

    async def get_products_links(self, category_link: str) -> list[str]:
        products_links = []
        soup = await self.get_soup(category_link)
        for product_item in soup.find_all("div", {"class": "product-item"}):
            products_links.append('https:' + product_item.find("div", {"class": "name"}).a['href'])
        return products_links

    async def get_product_info(self, product_link: str) -> list[Product] | None:
        art = None
        soup = await self.get_soup(product_link)
        name = soup.find("h1", {"itemprop": "name"}).string
        if translate('discount').lower() in name.lower() or translate('discount_2').lower() in name.lower():
            return []
        if art_tag := soup.find("meta", {"itemprop": "sku"}):
            art = art_tag['content']
        available = soup.find("div", {"class": "stock"}).string
        if available == translate('in_stock') or available == translate('in_stock_2'):
            available = '+'
        else:
            available = '-'
        price, old_price = None, None
        price_tag = soup.find("span", {"class": "price-default"})
        if price_tag:
            price = self.get_price(price_tag.string)
        else:
            price_tag = soup.find("span", {"class": "price-new", 'id': 'formated_special'})
            if price_tag:
                price = self.get_price(price_tag.string)
            price_tag_old = soup.find("span", {"class": "price-old", 'id': 'formated_price'})
            if price_tag_old:
                old_price = self.get_price(price_tag_old.string)

        return [Product(name=name,
                        art=art,
                        price=price,
                        old_price=old_price,
                        available=available,
                        link=product_link,
                        variant=None)]


Site().parse()
