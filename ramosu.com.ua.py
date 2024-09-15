from parser import Parser, Product


main_lang = 'ua'
lang = {
    'ua': {
        'site': 'https://ramosu.com.ua/uk/',
        'in_stock': 'у наявності',
        'kod': 'Код товару:',
    },
    'ru': {
        'site': 'https://ramosu.com.ua/',
        'in_stock': 'в наличии',
        'kod': 'Код товара:',
    }
}


def translate(element):
    return lang[main_lang][element]


class Site(Parser):
    price_file = 'Ramosu.xlsx'
    site = 'https://ramosu.com.ua/uk/'
    max_products_per_page = '?limit=100'

    async def get_categories_links(self, link: str) -> list[str]:
        podcat_links_arr = []
        soup = await self.get_soup(link)
        podcat_links = soup.find_all("a", {"class": "oct-menu-a"})
        for link in podcat_links:
            if link.span is not None:
                podcat_links_arr.append(link['href'])
        return podcat_links_arr

    async def get_products_links_per_page(self, page_link: str) -> list[str]:
        products_links = []
        soup = await self.get_soup(page_link)
        if soup.find('p', class_='empty-title'):
            return []
        for tag_item in soup.select_one("div.row.products-content").find_all("span", {"class": "h4-replace"}):
            products_links.append(tag_item.a['href'])
        return products_links

    async def get_products_links(self, category_link: str) -> list[str]:
        products_links = []
        soup = await self.get_soup(category_link + self.max_products_per_page)
        pagination = soup.find("ul", {"class": "pagination"})
        total_pages = 1
        if pagination is not None:
            pages = pagination.find_all("li")
            for page in reversed(pages):
                total_pages = int(page.a.string)
                break
        for i in range(1, total_pages + 1):
            next_page = f'{category_link}{"" if i == 1 else "page-" + str(i)}{self.max_products_per_page}'
            products_links.extend(await self.get_products_links_per_page(next_page))

        return products_links

    async def get_product_info(self, product_link: str) -> list[Product]:
        soup = await self.get_soup(product_link)
        name = soup.find("h1", {"class": "us-main-shop-title"}).string
        art = soup.find("span", {"class": "us-product-info-code"}).string
        # art = ''.join(re.findall(r'\d', art))

        available = soup.find("span", {"class": "us-product-info-is"}).text
        available = available.strip()
        if available.lower() == translate('in_stock'):
            available = '+'
        else:
            available = '-'

        price, old_price = None, None
        price = soup.find("div", {"class": "us-price-actual"})
        if price is not None:
            price = self.get_price(price.text)
        else:
            price = soup.find("div", {"class": "us-price-new"})
            if price is not None:
                price = self.get_price(price.text)
            old_price = soup.find("div", {"class": "us-price-old"})
            if old_price is not None:
                old_price = self.get_price(old_price.text)

        return [Product(name=name,
                        art=art,
                        price=price,
                        old_price=old_price,
                        available=available,
                        link=product_link,
                        variant=None)]


Site().parse()
