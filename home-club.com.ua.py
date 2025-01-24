from parser import Parser, Product
import re


def tag_has_sku(tag):
    return tag.has_attr('id') and 'sku' in tag['id']


class Site(Parser):
    price_file = 'home-club.com.ua.xlsx'
    site = 'https://home-club.com.ua/ua'
    render_javascript = True
    headless = False  # clouflare protection
    categories_to_get = [
        '/kukhonni-ostrivtsi-ta-vizky',
        '/moduli-na-kolesakh-dlia-vannoi',
        '/nastilni-lampy',
        '/svitlodiodne-osvitlennia',
        '/robochi-lampy',
        '/perenosni-svitylnyky',
    ]

    def get_price(self, price_str: str) -> int:
        return round(super().get_price(price_str) * 1.27)

    async def get_categories_links(self, link: str) -> list[str]:
        return [link + category for category in self.categories_to_get]

    async def get_products_links(self, category_link: str) -> list[str]:
        products_links = []
        page = 1
        while True:
            soup = await self.get_soup(f'{category_link}{"" if page == 1 else "?pagenumber=" + str(page)}')
            a_tags = soup.find('div', class_='product-grid').find_all('a')
            products_links.extend([self.site + a['href'].removeprefix('/ua') for a in a_tags if a.get('href')])
            if soup.find('li', class_='next-page'):
                page += 1
            else:
                break
        return products_links

    async def get_product_info(self, product_link: str) -> list[Product]:
        all_products = []
        soup = await self.get_soup(product_link)

        product = soup.find('div', class_='product-essential')

        name = product.find('h1').text

        art = product.find('div', class_='sku').find(tag_has_sku).text

        available = '-'
        available_tag = product.find(string=lambda text: 'Наявність у Львові:' in text).next_element
        if 'В наявності' in available_tag.text or re.findall('[1-9]', available_tag.text):
            available = '+'
        else:
            available_tag = product.find(string=lambda text: 'Наявність для поставки:' in text).next_element
            if 'В наявності' in available_tag.text or re.findall('[1-9]', available_tag.text):
                available = 'под заказ'

        price = self.get_price(product.find('div', class_='product-price').text)
        if old_price := product.find('div', class_='old-product-price'):
            old_price = self.get_price(old_price.text)

        all_products.append(Product(name=name,
                                    art=art,
                                    price=price,
                                    old_price=old_price,
                                    available=available,
                                    link=product_link,
                                    variant=None)
                            )
        return all_products


Site().parse()
