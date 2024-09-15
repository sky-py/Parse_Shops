from parser import Parser, Product
import json


class Site(Parser):
    price_file = 'sunuv.in.ua.xlsx'
    site = 'https://sunuv.in.ua/'
    compared_product_field = 'name'

    def get_price(self, price) -> int:
        our_price = int(round((float(price) - 100) * 1.25, 0))
        return our_price if our_price > 0 else 0

    async def get_categories_links(self, link: str) -> list[str]:
        soup = await self.get_soup(link)
        links = [a['href'] for a in soup.find(id="menu-osnovnoe").find_all('a') if
                     'https://sunuv.in.ua/uk/' not in a['href']]
        return links

    async def get_products_links(self, category_link: str) -> list[str]:
        soup = await self.get_soup(category_link + self.max_products_per_page)
        try:
            products_links = [li.a['href'] for li in soup.select_one(".products.columns-3").find_all('li')]
            return products_links
        except AttributeError:
            return []

    async def get_product_info(self, product_link: str) -> list[Product]:
        all_products = []
        soup = await self.get_soup(product_link)
        name = soup.find('h1').text
        if products_json := soup.find('form', class_='variations_form'):
            for product in json.loads(products_json['data-product_variations']):
                variant = ' - '.join(product['attributes'].values())
                all_products.append(Product(name=f'{name} - {variant}',
                                            art=product['sku'],
                                            price=self.get_price(product['display_price']),
                                            old_price=None,
                                            available='+' if product['is_in_stock'] else '-',
                                            link=product_link,
                                            variant=variant)
                                    )
        elif products_json := soup.find('script', class_="", attrs={'type': 'application/ld+json'}):
            product = json.loads(products_json.text)['@graph'][1]
            all_products.append(Product(name=name,
                                        art=product['sku'],
                                        price=self.get_price(product['offers'][0]['price']),
                                        old_price=None,
                                        available='+' if 'InStock'.lower() in product['offers'][0][
                                            'availability'].lower() else '-',
                                        link=product_link,
                                        variant=None)
                                )
        return all_products


Site().parse()
