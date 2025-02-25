from parser import Parser, Product


def get_our_price(price: int) -> int:
    return round(price * 1.25)


class Site(Parser):
    price_file = 'artofchoice.xlsx'
    site = 'https://artofchoice.ua/ru/catalog/'
    number_of_workers = 1
    compared_product_field = 'name'

    async def get_categories_links(self, link: str) -> list[str]:
        return [link]

    async def get_products_links(self, category_link: str) -> list[str]:
        return [category_link]

    async def get_product_info(self, product_link: str) -> list[Product]:
        all_products = []
        soup = await self.get_soup(product_link)
        
        for product_block in soup.find_all('td', valign='top'):
            name_tag = product_block.find('h2')
            price_tag = product_block.find('td', class_='price')

            if name_tag and price_tag:
                name = name_tag.get_text().strip()
                price = get_our_price(self.get_price(price_tag.get_text()))
                all_products.append(Product(name=name,
                                            art=name,
                                            available='+',
                                            price=price,
                                            link=product_link
                                            ))

        return all_products


Site().parse()
