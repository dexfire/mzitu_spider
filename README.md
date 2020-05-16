# mzitu_spider
妹子图 | 图集爬虫 [https://www.mzitu.com](https://www.mzitu.com])

## Usage

Tested on Python 3.7 under Windows 10.

Just type like this:
`python3 mzitu.py`

It will collect some necessary infomation then scraping the little website.

if you need to specify a proxy server, please modify the `__init__()` function like this:

```python
self.proxy = {
    "http": "http://127.0.0.1:1087",
    "https": "http://127.0.0.1:1087",
    "all": "http://127.0.0.1:1087"
}
```

## Known issues
1. HTTP 429 Code  

It was caused by the website attack protection system, wait for a moment, or using a proxy pool!

## About
Welcome visiting [my blog](https://dexfire.cn).

## License
[MIT](LICENSE)
