from parser import Parser, Product
import os
from dotenv import load_dotenv


load_dotenv('/etc/env/suppliers.env')


class Site(Parser):
    price_file = 'gsdm.xlsx'
    site = 'https://gsdm.com.ua/'
    max_products_per_page = '?limit=500'
    login_data = {
        'email': os.getenv('gsdm_login'),
        'password': os.getenv('gsdm_password')
    }

    async def login(self, login_data: dict) -> bool:
        await self.get_soup(self.site)
        r = await self.client.post(self.site + 'login/', data=login_data)
        return 'Мій обліковий запис' in r.text

    def get_price(self, price_str: str) -> int:
        return int(super().get_price(price_str) * 1.06 * 1.25)

    async def get_categories_links(self, link: str) -> list[str]:
        if not await self.login(self.login_data):
            raise Exception('Login failed')
        categories_links = ['stilci/']
        return [self.site + category_link for category_link in categories_links]


    async def get_products_links(self, category_link: str) -> list[str]:
        products_links = []
        soup = await self.get_soup(category_link + self.max_products_per_page)
        products = soup.find_all('div', {'class': 'product-layout'})
        for product in products:
            for a in product.find_all('a'):
                products_links.append(a['href'])
        return products_links

    async def get_product_info(self, product_link: str) -> list[Product]:
        soup = await self.get_soup(product_link)
        name = soup.find('h1').string

        art_tag = soup.find('li', string=lambda txt: txt and 'Модель:' in txt)
        art = art_tag.string.split(': ')[1]

        available_tag = soup.find('li', string=lambda txt: txt and 'Наявність:' in txt)
        if available_tag and 'є в наявності' in available_tag.string.lower():
            available = '+'
        else:
            available = '-'

        price, old_price = 0, None
        if price_tag := soup.find('span', {'class': 'autocalc-product-price'}):
            price = self.get_price(price_tag.string)
        if new_price_tag := soup.find('span', {'class': 'autocalc-product-special'}):
            price, old_price = self.get_price(new_price_tag.string), price

        return [Product(name=name,
                        art=art,
                        price=price,
                        old_price=old_price,
                        available=available,
                        link=product_link,
                        variant=None)]


Site().parse()
