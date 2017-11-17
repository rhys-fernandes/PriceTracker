import json
import sqlite3
import time
from datetime import datetime
import concurrent.futures
from re import sub

import pyexcel as pe
import requests
from lxml import html
from pushbullet import PushBullet
# from fake_useragent import UserAgent

# Used for PushBullet Notification
class Notify:
    def __init__(self, title, link):
        self.__api = ""
        self.__title = title
        self.__link = link
        self.pb = PushBullet(self.__api)

    def push(self, message):
        self.pb.push_link(self.__title, self.__link, body=str(message))


class Item(Notify):

    # class variable to hold price data of all items (exported as json)
    price_data = {}

    def __init__(self, item_name, item_link, website, price_limit):

        # for pushbullet notifications
        super().__init__(item_name, item_link)

        self.item_name = item_name
        self.item_link = item_link
        self.price_limit = float(price_limit)

        # xpath retrieved form database depending on website
        self.__query = self.get_xpath(website)
        self.__xpaths = {"xpath": self.__query[0],
                         "xpath_sale": self.__query[1], }

        # old data is read into price_data, new item are added if not in data
        with open('Price_Data.json', 'r+') as file:
            Item.price_data = json.load(file)
            if self.item_name not in Item.price_data:
                Item.price_data.update({self.item_name: {"price": [],
                                                         "notification": True,
                                                         "link": self.item_link
                                                         }})
            file.seek(0)
            file.write(json.dumps(Item.price_data))
            file.truncate()

    def __repr__(self):
        # noinspection PyPep8
        return "{self.__class__.__name__}({self.item_name}, {self.price_limit})".format(self=self)

    def get_price(self):
        """
        attempts to retrieve the price of an item, given 3 tries
        5 sec delay with each attempt

        :return: Item price (float)
        """

        price = None
        # ua = UserAgent()
        attempts = 3
        # print(ua.random)

        while (price is None) and (attempts > 0):

            # header = {'User-Agent': str(ua.random)}

            page = requests.get(self.item_link)
            tree = html.fromstring(page.content)
            original = tree.xpath('{}/text()'.format(self.__xpaths["xpath"]))
            sale = tree.xpath('{}/text()'.format(self.__xpaths["xpath_sale"]))

            attempts -= 1

            if original or sale:
                price = original or sale
            else:
                time.sleep(5)

        return float(sub(r'[^0-9.]', '', price[0]))

    def price_check(self):
        """
        compares the retrieved get_price to the desired price
        :return: pushbullet notification is sent if lower or equal to
        """
        current_price = self.get_price()

        if (current_price <= self.price_limit) \
                and Item.price_data[self.item_name]["notification"] is True:
            Item.price_data[self.item_name]["notification"] = False
            self.push(message="Item on sale at £{}".format(current_price))

    def export_data(self):
        """
        function updates the json file with up to date data
        :return: write to json file
        """
        d = datetime.today().strftime('%Y-%m-%d-%H-%M')

        with open("Price_Data.json", "r+") as file:
            # noinspection PyPep8
            Item.price_data[self.item_name]["price"].append([d, self.get_price()])
            file.seek(0)
            file.write(json.dumps(Item.price_data))
            file.truncate()

    @staticmethod
    def get_xpath(_):
        """
        used to get correct xpath for an item given the website
        :param _: Item website (lowercase)
        :return: xpath (string)
        """
        conn = sqlite3.connect("xpath_data")

        with conn:
            data = conn.execute(
                "SELECT xpath, xpath_sale FROM xpath_data WHERE name=?", (_,))
            return data.fetchall()[0]


def main():
    def multi_create(i):

        return Item(i["ITEM NAME"],
                    i["ITEM LINK"],
                    i["WEBSITE"].lower(),
                    i["DESIRED PRICE"])

    def multi_exe(i):
        try:
            i.price_check()
            i.export_data()
            print("Task complete: {}".format(i))

        except ValueError as e:
            print("Error with {}, {}".format(i.item_name, e))

    records = pe.iget_records(file_name="Item_List.xlsx")
    filtered_records = [x for x in records if x["ITEM NAME"] != ""]
    pe.free_resources()
    # print(records)

    start = time.time()

    with concurrent.futures.ThreadPoolExecutor() as exe:
        item_instances = exe.map(multi_create, filtered_records)
        print("Instances Created: {:.2f}".format(time.time() - start))
        exe.map(multi_exe, item_instances)

    print("End: {:.2f} seconds".format(time.time() - start))


if __name__ == '__main__':
    main()
