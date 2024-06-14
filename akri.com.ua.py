import time
from parcer import Parcer, Product
import json


def get_number(price: str) -> int:
    price = int(round(float(price), 0))
    return price if price > 0 else 0


def get_number_from_content(content: str) -> int | None:
    if price := content.split('.'):
        return int(price[0])
    else:
        return None


class Site(Parcer):
    price_file = 'akri.com.ua.xlsx'
    site = 'https://akri.com.ua/ua/'
    number_of_workers = 2
    max_products_per_page = '?limit=500'
    compared_product_field = 'name'

    async def get_categories_links(self, link: str) -> list:
        soup = await self.get_soup(link)
        links = [li.a['href'].replace('http://', 'https://')
                 for li in soup.find('nav', class_='side-nav').ul.find_all('li', recursive=False)]
        return links

    async def get_products_links(self, category_link: str) -> list:
        soup = await self.get_soup(category_link)
        try:
            products_links = [a['href'].replace('http://', 'https://')
                              for a in soup.find('div', class_='products').find_all('a')]
            return products_links
        except:
            return []

    async def get_product_info(self, product_link: str) -> list[Product] | None:
        all_products = []
        soup = await self.get_soup(product_link)

        old_price = soup.find('span', class_='old-price')
        if old_price:
            old_price = get_number_from_content(old_price.text)

        for script_tag in soup.find_all('script', attrs={'type': 'application/ld+json'}):
            product = json.loads(script_tag.text)
            if product.get('@type').lower() == 'product':
                price = get_number(product['offers']['price'])
                all_products.append(Product(name=product['name'],
                                            art=product['sku'],
                                            price=price,
                                            old_price=old_price,
                                            available='+' if 'InStock'.lower() in product['offers']['availability'].lower() else '-',
                                            link=product_link,
                                            variant=None)
                                    )
        if not all_products:
            print('****************   NO PRODUCTS FOUND ON THE PAGE  ******************')
            with open(str(time.time()).split('.')[0], mode='w', encoding='utf-8') as f:
                f.write(f'{product_link}\n{soup.prettify()}')
        return all_products


Site().parse()
