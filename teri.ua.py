import re
from parcer import Parcer, Product


class Site(Parcer):
    price_file = 'teri.ua.xlsx'
    site = 'https://teri.ua/'
    use_discount = False

    proxy_host = '5.44.252.176'  # "your_proxy_host"
    proxy_port_http = 28000
    proxy_port_https = 28800
    # proxy_username = 'proxy'
    # proxy_password = 'FoxyProxy'

    async def get_categories_links(self, link: str) -> list[str]:
        soup = await self.get_soup(link)
        menu = soup.find('ul', {'id': 'top-menu'}).find(lambda tag: tag.string == 'Каталог').parent.ul
        links = [li.a['href'] for li in menu.select('li:not(.menu-item-has-children)')]
        return links

    async def get_products_links(self, category_link: str) -> list[str]:
        soup = await self.get_soup(category_link)
        try:
            products_links = [li.a['href'] for li in soup.select_one('ul.products.columns-4').find_all('li')]
            return products_links
        except:
            return []

    async def get_product_info(self, product_link: str) -> list[Product] | None:
        old_price = None
        soup = await self.get_soup(product_link)

        data = soup.find('meta', attrs={'name': 'pm-dataLayer-meta'}).find_next().text
        art = re.findall(r'"sku":"(.+?)"', data, re.DOTALL)[0]
        name = re.findall(r'"name":"(.+?[^\\])"', data, re.DOTALL)[0].replace('\\', '')

        price_tag = soup.find('div', class_='et_pb_wc_price')
        if not price_tag:
            price_tag = soup.find('div', class_='entry-summary').find('p', class_='price')

        if price_tag.find('ins'):
            price = self.get_price(price_tag.find('ins').text)
        else:
            price = self.get_price(price_tag.text)

        try:
            old_price = price_tag.find('del').text
            old_price = self.get_price(old_price)
        except:
            pass

        return [Product(name=name,
                        art=art,
                        price=price,
                        available='+',
                        old_price=old_price,
                        link=product_link,
                        variant=None)]


Site().parse()
