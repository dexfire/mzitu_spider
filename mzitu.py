# coding=utf8
import os
import re
import csv
import json
import time
import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup


class MzituSpider(object):
    """
    妹子图： https://m.mzitu.com
    ------------------------------------

    使用 request+bs4，没有使用框架。
    测试中可能出现请求频繁，已增加处理机制可以稳定爬取。
    无需使用代理池，所以爬的速度会比较慢。
    """

    # 妹子图练手
    def __init__(self, sleep_time=60, retry_times=3, proxy=None, update=False, only_update_first_page=True):
        self.debug = False
        self.debug_level = 3
        self.url = "https://m.mzitu.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
            "Referer": "https://m.mzitu.com",
            'Accept-Encoding': 'gzip, deflate',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        
        ## Specify you proxy settings here!
        # just uncomment and modify below:
        #
        #   self.proxy = {
        #       "http": "http://127.0.0.1:1087",
        #       "https": "http://127.0.0.1:1087",
        #       "all": "http://127.0.0.1:1087"
        #   }
        #
        # note: also remember to comment the line below.

        self.proxy={}

        self.start_time = datetime.now()
        self.req = requests.Session()
        self.retry_times = retry_times     # 请求失败后的重试次数
        self.sleep_time = sleep_time       # 请求频繁后的休眠时间
        self.update = update
        self.only_update_first_page = only_update_first_page
        if not os.path.exists("data"):
            os.mkdir("data")
        if not os.path.exists("log"):
            os.mkdir("log")
        self.log_path = ""                  # 占位符，在下一个函数调用中被初始化
        self.init_logging()
        self.log_Info("开始爬取：" + self.url +
                      os.linesep + "请求头：" +
                      os.linesep + ", ".join([k+": "+self.headers[k] for k in self.headers]))
        self.history_gallerys_path = "data" + os.sep + "history.json"

        self.success_gallerys_id = set()       # 记录失败的 图集id
        self.failed_gallerys_id = set()            # 记录失败的 图集id
        self.history_gallerys = {}          # 记录爬取的页面信息(Pages)
        # self.gallerys_info
        try:
            with open(self.history_gallerys_path, "r", encoding="utf8") as f:
                self.history_gallerys = json.load(f)
                self.success_gallerys_id = set(self.history_gallerys.get(
                    "success_gallerys_id", set()))
                self.failed_gallerys_id = set(self.history_gallerys.get(
                    "failed_gallerys_id", set()))
                self.log_Info("读取爬虫日志成功！" + os.linesep +
                              "已有图库数据：" + str(len(self.success_gallerys_id)) + "/" + str(len(self.history_gallerys) - 2))
        except Exception as e:
            self.log_warn("读取爬虫日志错误！请参阅日志文件：" + self.log_path)
            self.log.exception(e)

        """
        数据格式：
            {
                "210018":
                    {
                        "home_page": 1,   # 无意义，会随着主页更新而改变
                        "title": "粉嫩胴体高清特写！小清新美女徐微微mia泳池上演脱衣秀",
                        "url": "https://www.mzitu.com/210018"
                        "gallery_id": 210018,
                        "cover_pic_url": "https://i.mmzztt.com/thumb/2020/03/210018_236.jpg" # 可能不存在
                        "pics": 93
                        "error_pic_url": [],
                        "status": "empty"  # empty - 未完成, success - 成功, failed - 失败
                        "pics_url":
                            [
                                "https://i3.mmzztt.com/2019/11/03c01.jpg",
                                "https://i3.mmzztt.com/2019/11/03c74.jpg"
                            ]
                    },
                "210019":
                    { ... },

                ...

                "success_gallerys_id":                  # 成功的图册，用作是否跳过的依据
                    ["210018", ...]

                "failed_gallerys_id":                   # 仅作记录，不作为访问使用参考
                    ["210019", ...]
            }
        """

    def loadBasic(self):
        try:
            resp = self.req.get(
                self.url, headers=self.headers, proxies=self.proxy)
        except Exception as e:
            self.log_warn("首页信息获取失败！重试！")
            self.log.exception(e)
            try:
                resp = self.req.get(
                    self.url, headers=self.headers, proxies=self.proxy)
            except Exception:
                self.log_warn("首页信息获取失败！")
                exit(0)

        if resp.ok:
            self.log_info("获取首页成功！")
            bs = BeautifulSoup(resp.text, features="lxml")
            next_page = bs.find("a", attrs={"class": "next page-numbers"})
            self.title = bs.find("title").text
            self.log_info("Title: " + self.title)
            self.log_info("URL: " + resp.url)
            self.total_pages = int(next_page.findPreviousSibling("a").text)
            self.log_info("总页面数目：" + str(self.total_pages))
            self.log_info("下一页URL：" + next_page.attrs['href'])

    def loadPagesData(self, start: int = -1, end: int = -1):
        """
        依次获取全部页面信息
        """
        self.log_Info("开始获取页面信息！")
        if 'postlist' not in self.history_gallerys:
            self.history_gallerys['postlist'] = {}

        for p in range(1, self.total_pages+1):
            if self.debug and self.debug_level >= 3:
                self.log_info("开始获取第 "+str(p)+"/"+str(self.total_pages)+" 页")
            page_url = self.url + "/page/" + str(p) + "/"
            retry = self.retry_times
            presp = self.req.get(
                page_url, headers=self.headers, proxies=self.proxy)
            while (not presp.ok) and (retry > 0):
                self.sleep("获取页面 page: " + str(p) + "失败")
                retry = retry - 1
                self.log_info("重试计数：" + str(retry))
                presp = self.req.get(
                    page_url, headers=self.headers, proxies=self.proxy)
            if presp.ok:
                self.log_info("Loading "+str(p)+"/" +
                              str(self.total_pages)+" page...")
                bs = BeautifulSoup(presp.text, features="lxml")
                # covers = bs.find(
                #     "div", attrs={"class": "postlist"}).findChildren("img")
                # links = [c.findParent() for c in covers]
                # { gid:, title:, url:, }
                posts = [i.findParent() for i in bs.find(
                    "div", attrs={"class": "postlist"}).findChildren("img")]
                dic = {self.get_gid(p.attrs['href']): {"gid": self.get_gid(
                    p.attrs['href']), "url": p.attrs['href'], "title": p.findChild("img").attrs['alt'], "cover": self.getCover(p)} for p in posts}
                self.log_Info("含"+str(len(posts))+"个图集" + os.linesep + os.linesep.join(
                    ["#"+g+" "+dic[g]['title'] + " @ " + dic[g]['url'] for g in dic]))
                self.history_gallerys['postlist'].update(dic)
                time.sleep(0.01)
        # 保存结果
        with open("data" + os.sep + "history.json", "w") as f:
            # 重新转化成功、失败记录set为list，方便序列化
            self.history_gallerys["success_gallerys_id"] = list(
                self.success_gallerys_id)
            self.history_gallerys["failed_gallerys_id"] = list(
                self.failed_gallerys_id)
            json.dump(self.history_gallerys, f)
        # 输出页面信息为 CSV 文件
        csv_output_path = "data"+os.sep+"postlist.csv"
        with open(csv_output_path, "w", encoding="utf8", newline="") as fp:
            csv_output = csv.DictWriter(fp, fieldnames=[
                "gid", "title", "url", "cover"], extrasaction="ignore")
            csv_output.writeheader()
            csv_output.writerows([self.history_gallerys['postlist'][k]
                                  for k in self.history_gallerys['postlist']])
            fp.flush()
            fp.close()
        # pass

    def beginTask(self):
        """
        开始完整爬取任务
        ----------------------
        任务层次：
        - 首页(Page #1)          [页面]
            - 图集1              [图集]
                - 图片1          [图片]
                - 图片2          [图片]
                ...              [图片]
            - 图集2              [图集]
            ...                  [图集]
        - Page #2                [页面]
        ...                      [页面]
        ----------------------
        1. 首先读取 history.json 获取成功和失败的页面
            {
                "history_gallerys": {"1": [{...}, {...}, ...], "2":[...], ...}, // 爬取过的图集
                "success_gallerys": ["1", "2", ...] // 完成的页面
            }
        2. 首先获取页数，然后遍历页数，对成功爬取过的页面：**跳过**；
        - 对内容中的每个图集，首先检查是否存在 no_error.txt 存在的话跳过，并追加日志；
        - 对于日志中成功(finished)图集：跳过，并检测是否存在 no_error.txt， 不存在则追加标记；
        - 获取日志中失败的图集，检查原因，如果是empty，全新遍历；failed，
        - 获取页面中的错误，如果单个图片错误，记录出错的图片，存放在图集中的错误图片URL中
        """
        # 读取页面信息（总页面数目等）
        self.loadBasic()
        # 如有需要，重新获取所有图集列表
        if self.update:
            self.loadPagesData()
        # 开始获取数据
        for gallery in self.history_gallerys["postlist"]:
            self.loadGallery(self.history_gallerys["postlist"][gallery]["url"])

        """
        # ================= 获取页面（Pages） =================
        for p in range(1, self.total_pages + 1):
            page_url = self.url + "/page/" + str(p) + "/"
            try:
                retry = 3
                resp = self.req.get(
                    page_url, headers=self.headers, proxies=self.proxy)
                while (not resp.ok) and (resp.status_code == 429) and (retry > 0):
                    self.log_Info("获取页面失败，休眠 60s 防止被封IP...")
                    time.sleep(60)
                    self.log_info(
                        "第"+str(retry) + "次重试，第" + str(p) + "页...")
                    resp = self.req.get(
                        page_url, headers=self.headers, proxies=self.proxy)
                    retry = retry - 1

                if resp.ok:
                    bs = BeautifulSoup(resp.text, features="lxml")
                    covers = bs.find(
                        "div", attrs={"class": "postlist"}).findChildren("img")
                    links = [c.findParent() for c in covers]

                    # 记录日志
                    if self.debug and self.debug_level >= 1:
                        self.log_info("读取第 " + str(p) + " 页成功！")

                    if self.debug and self.debug_level >= 3:
                        self.log_Info(os.linesep.join(
                            [">> #" + self.get_gid(c.findParent().attrs["href"]) + " : " + c.attrs['alt'] for c in covers if c.attrs['alt'] != "下载妹子图APP"]))  # 打印标题
                        self.log.info("相关链接：" + os.linesep + os.linesep.join(
                            [l.attrs['href'] for l in links]))  # 记录链接
                    # ================= 获取图集（Gallerys） =================
                    # 获取图集链接，筛选掉带有app的项目（广告）
                    for i, gallery_link in enumerate([l.attrs['href'] for l in links if ("app" not in l.attrs['href'])]):
                        # 注：跳过 https://www.mzitu.com/app/
                        # if "app" not in gallery_link:
                        gid = self.get_gid(gallery_link)
                        if gid in self.success_gallerys_id:
                            self.log_info("☆ 棒棒哒的图集 #" + str(gid) + ": " +
                                          self.history_gallerys[gid]["title"])
                            continue
                        elif gid in self.history_gallerys and self.history_gallerys[gid]["status"] == "failed":
                            # TODO: 只需要处理错误的项目即可
                            pass
                        else:
                            payback = self.loadGalleryContents(gallery_link)
                            payback["home_page"] = p
                            # 'alt' in covers[i].attrs and ...
                            if 'data-original' in covers[i].attrs:
                                # payback["title"] = covers[i].attrs['alt']
                                payback["cover_pic_url"] = covers[i].attrs['data-original']
                            elif 'src' in covers[i].attrs:
                                # payback["title"] = covers[i].attrs['alt']
                                payback["cover_pic_url"] = covers[i].attrs['src']
                            else:
                                self.log_info(
                                    "未找到 data-original/src 字段！ Page: " + str(p) + " URL: " + gallery_link)
                                self.log.warn(str(covers[i]))

                            # 增加日志记录
                            try:
                                if "gallery_id" in payback:
                                    self.history_gallerys[gid] = payback
                            except Exception:
                                self.log_warn("记录 payback 出错！")
                            # if "status" in payback and payback["status"] == "success":
                            #     self.success_gallerys_id.add()

                            # 保存单个图集日志（仅供后续统计使用）
                            path = "data"+os.sep + \
                                payback["gallery_id"]+os.sep + \
                                payback["gallery_id"]+"_page_info.json"
                            with open(path, "w", encoding="utf8") as fp:
                                json.dump(payback, fp)
                            self.log_info("页面信息：" + os.path.abspath(path))
                            # 保存全部爬取日志

                        # 备份（重命名）原有日志
                        # if os.path.exists(self.history_gallerys_path):
                        #     os.rename(self.history_gallerys_path, "data" + os.sep + "history_gellerys_" +
                        #               datetime.now().strftime(r"%Y-%m-%d__%H.%M.%S") + ".json")

                        # 重写日志
                        with open("data" + os.sep + "history.json", "w") as f:
                            # 重新转化成功、失败记录set为list，方便序列化
                            self.history_gallerys["success_gallerys_id"] = list(
                                self.success_gallerys_id)
                            self.history_gallerys["failed_gallerys_id"] = list(
                                self.failed_gallerys_id)
                            json.dump(self.history_gallerys, f)

            except Exception as e:
                self.log_warn("读取页面出错:" + page_url)
                self.log.exception(e)
                self.sleep("获取页面失败")
        """

    def loadGalleryContents(self, link: str):
        """
        获取单个图集所有图片，
        通常一个页面包含90多个图片。
        """
        self.log.info("开始处理：" + link)
        # 获取 GalleryID:
        # "https://www.mzitu.com/210018" -> gid = "210018"
        # re.search(r"/([0-9]+)/?", link).group(1)
        gid = self.get_gid(link)
        # 图集数据
        pinfo = {
            "gallery_id": gid,
            "url": link,
            "pics_url": [],
            "error_pic_url": [],
            "status": "empty"  # empty - 未完成, success - 成功, failed - 失败
        }
        if gid in self.history_gallerys:
            pinfo.update(self.history_gallerys[gid])
        # 图集基础数据文件夹
        folder_path = "data" + os.sep + gid
        if not os.path.exists(folder_path):
            # 创建文件夹
            os.mkdir(folder_path)

        if self.debug and self.debug_level >= 2:
            self.log_info("爬取页面ID：" + str(gid) + " " + link)
            self.log_info("工作文件夹：" + os.path.abspath(folder_path))
        # ================= 获取第一页（抽取图片数量） =================
        resp = self.req.get(link, headers=self.headers, proxies=self.proxy)
        if resp.ok:
            bs = BeautifulSoup(resp.text, features="lxml")
            title = bs.find("title").text
            pinfo["title"] = title
            self.log_info("标题：" + title)
            # 获取页面的标签
            tags = bs.find(
                "div", attrs={"class": 'main-tags'}).findChildren("a")
            pinfo["tags"] = {tag.text: tag.attrs["href"] for tag in tags}
            # 获取总图集大小
            next_page = bs.find("span", text="下一页»")  # 不同于首页的next_page
            if next_page is not None:
                # 数值类型
                pages = int(next_page.findParent(
                ).findPreviousSibling("a").text)

                if self.debug and self.debug_level >= 3:
                    self.log_info("总图片数目：" + str(pages))
                pinfo['pics'] = pages
                # 判断是否是已经爬取完成的图集（判断no_error.txt文件是否存在）
                noerror = folder_path + os.sep + "no_error.txt"
                # 测试模式，不考虑已存在的文件  True or
                if not os.path.exists(noerror):
                    errors = 0
                    # ================= 依次获取图片描述页面 =================
                    # 依次爬取图集图片
                    for pp in range(1, pages+1):
                        ppurl = "https://www.mzitu.com/" + \
                            str(gid) + "/" + str(pp)
                        headers = self.headers
                        headers["Referer"] = ppurl
                        path = folder_path + os.sep + \
                            "mz_" + str(pp) + ".jpg"
                        if not os.path.exists(path) or (os.path.exists(path) and os.path.getsize(path) == 18792):
                            try:  # 开始读取页面
                                respp = self.req.get(
                                    ppurl, headers=headers, proxies=self.proxy)
                                if respp.ok:
                                    try:
                                        # ================= 抽取图片链接 =================
                                        bs = BeautifulSoup(
                                            respp.text, features="lxml")
                                        img_url = bs.find(
                                            "div", attrs={"class": "main-image"}).findChild("img").attrs["src"]
                                        pinfo['pics_url'].append(img_url)

                                        # 判断是否已经存在正确文件
                                        if (not os.path.exists(path)) or (os.path.exists(path) and os.path.getsize(path) == 18792):
                                            # ================= 获取图片数据 =================
                                            img_resp = self.req.get(
                                                img_url, headers=self.headers, proxies=self.proxy)
                                            pretry = 3
                                            while (not img_resp.ok) and (img_resp.status_code == 429) and (pretry > 0):
                                                self.log_Info(
                                                    "获取图片数据失败，错误代码：" + str(img_resp.status_code))
                                                # 休眠防止封禁 IP
                                                self.sleep()
                                                self.log_info(
                                                    "第"+str(pretry) + "次重试: #" + str(gid) + ": " + title)
                                                img_resp = self.req.get(
                                                    img_url, headers=self.headers, proxies=self.proxy)
                                                pretry = pretry - 1
                                            # 存储图片数据
                                            if "image/jpeg" == img_resp.headers["Content-Type"] or "image/jpg" == img_resp.headers["Content-Type"]:
                                                # path = "data" + os.sep + gid + os.sep + "mz_" + str(pp) + ".jpg"
                                                fpp = open(path, "wb")
                                                fpp.write(img_resp.content)
                                                fpp.close()
                                                # 记录日志
                                                if self.debug and self.debug_level >= 3:
                                                    self.log_info(
                                                        "#" + gid + ": " + img_resp.headers["Content-Length"] + "@" + path)
                                                else:
                                                    self.log.info(
                                                        "#" + gid + ": " + img_resp.headers["Content-Length"] + "@" + path)
                                                time.sleep(0.05)  # 休眠0.1s
                                            elif "text/html" == img_resp.headers["Content-Type"]:
                                                # ================= 频繁访问情况 =================
                                                # 当频繁访问时，返回 429 错误
                                                errors = errors + 1
                                                pinfo["error_pic_url"].append(
                                                    img_url)

                                                self.log_info(
                                                    "获取图片失败，错误代码: " + str(img_resp.status_code))
                                                # 休眠防止封禁 IP
                                                self.sleep()

                                                path = folder_path + os.sep + \
                                                    "mz_" + str(pp) + ".html"
                                                fpp = open(path, "wb")
                                                fpp.write(img_resp.content)
                                                fpp.close()
                                                # 记录错误日志
                                                if self.debug and self.debug_level >= 3:
                                                    self.log_info(
                                                        "#" + gid + ": " + img_resp.headers["Content-Length"] + " @" + path)
                                                else:
                                                    self.log.info(
                                                        "#" + gid + ": " + img_resp.headers["Content-Length"] + " @" + path)
                                                self.failed_gallerys_id.add(
                                                    gid)
                                                if gid in self.success_gallerys_id:
                                                    self.success_gallerys_id.remove(
                                                        gid)
                                            else:
                                                # 其他数据类型错误
                                                errors = errors + 1
                                                self.log_warn("图片非JPG格式，实际类型：" +
                                                              img_resp.headers["Content-Type"])
                                                self.failed_gallerys_id.add(
                                                    gid)
                                                if gid in self.success_gallerys_id:
                                                    self.success_gallerys_id.remove(
                                                        gid)
                                        else:
                                            self.log_info(
                                                "文件已存在：" + "#" + gid + ": " + str(os.path.getsize(path)) + " @" + path)

                                        # end if (not os.path.exists(path)) or (os.path.exists(path) and os.path.getsize(path) == 18792)
                                        # ================= 获取图片结束 =================
                                    except Exception as e:
                                        self.log_warn("获取页面内容出错：" + link)
                                        self.log.exception(e)
                                        self.failed_gallerys_id.add(gid)
                                        if gid in self.success_gallerys_id:
                                            self.success_gallerys_id.remove(
                                                gid)
                                else:
                                    self.log_warn("获取MZ单图页面失败：" + gid +
                                                  " -> #" + str(pp))
                                    self.log_info(
                                        "Request: " + str(respp.status_code) + " @ " + respp.url)
                                    self.failed_gallerys_id.add(gid)
                                    if gid in self.success_gallerys_id:
                                        self.success_gallerys_id.remove(gid)
                                    if respp.status_code == 429:
                                        # 休眠防止封禁 IP
                                        self.sleep()
                                # end if respp.ok:
                            except Exception as e:
                                # except requests.exceptions.SSLError as e:
                                # 处理描述页面连接错误
                                self.log_warn("SSL连接失败！")
                                self.log.exception(e)
                                self.failed_gallerys_id.add(gid)
                                if gid in self.success_gallerys_id:
                                    self.success_gallerys_id.remove(gid)
                                # 休眠防止封禁 IP
                                self.sleep()
                        else:
                            self.log_info(
                                "文件已存在：" + "#" + gid + ": " + str(os.path.getsize(path)) + " @" + path)
                    # ================= 获取图片描述页面结束 =================
                    # end for pp in range(pages+1)
                    # 页面图片处理完成，如果没有错误，生成一个标志文件，避免下次遍历判断
                    if errors == 0:
                        pinfo["status"] = "success"
                        noerror = folder_path + os.sep + "no_error.txt"
                        with open(noerror, "w", encoding="utf8") as f:
                            f.write("OK!" + os.linesep +
                                    "Files Count:" + str(pages))
                            f.close()
                        self.log_Info("图集读取成功！ " + str(gid) +
                                      ", " + str(pages) + " pics.")
                        # 增加成功记录！
                        self.success_gallerys_id.add(gid)
                        if gid in self.failed_gallerys_id:
                            self.failed_gallerys_id.remove(gid)
                    else:
                        pinfo["status"] = "failed"
                    # 生成一个以标题命名的信息文本，无论失败与否
                    title_fn = re.sub("[<:*>?|\\/\"]", "", title)
                    with open(folder_path + os.sep + title_fn + ".txt", "w", encoding="utf8") as fpp:
                        fpp.write(title)
                        fpp.write("URL: " + resp.url)
                        fpp.close()
                else:
                    # 存在 no_error.txt 文件
                    self.log_info("☆ 棒棒哒的图集 #" + str(gid) + ": " + title)
                    title_fn = re.sub("[<:*>?|\\/\"]", "", title)
                    with open(folder_path + os.sep + title_fn + ".txt", "w", encoding="utf8") as fpp:
                        fpp.write(title)
                        fpp.close()
                    # 增加成功记录！
                    self.success_gallerys_id.add(gid)
                    if gid in self.failed_gallerys_id:
                        self.failed_gallerys_id.remove(gid)
                    # TODO 弥补日志缺失
                    """jpath = folder_path + os.sep + gid + "_page_info.json"
                    if os.path.exists(jpath):
                        with open(jpath, "r", encoding="utf8") as fpp:
                            # 读取本地文件信息
                            print(json.load(fpp))
                            pinfo = json.load(fpp).update(pinfo)
                            print(pinfo)
                            # pinfo["title"] = title
                            # if "page_id" in pinfo:
                            #     pinfo["gallery_id"] = pinfo["page_id"]"""
                # end if not os.path.exists(noerror):
            else:
                self.log_warn("未找到“下一页”标签，无法判断图片数量！")
                self.failed_gallerys_id.add(gid)
                if gid in self.success_gallerys_id:
                    self.success_gallerys_id.remove(gid)
            # end if next_page is not None:
        else:
            self.log_warn("获取页面" + gid + "失败！")
            self.failed_gallerys_id.add(gid)
            if gid in self.success_gallerys_id:
                self.success_gallerys_id.remove(gid)
        return pinfo

    def loadGallery(self, gallery_link: str):
        # 注：跳过 https://www.mzitu.com/app/
        # if "app" not in gallery_link:
        gid = self.get_gid(gallery_link)
        if gid in self.success_gallerys_id and gid in self.history_gallerys:
            self.log_info("☆ 棒棒哒的图集 #" + str(gid) + ": " +
                          self.history_gallerys[gid]["title"])
            return
        elif gid in self.history_gallerys and self.history_gallerys[gid]["status"] == "failed":
            # TODO: 只需要处理错误的项目即可
            pass
        else:
            payback = self.loadGalleryContents(gallery_link)
            # 'alt' in covers[i].attrs and ...

            # 增加日志记录
            try:
                if "gallery_id" in payback:
                    self.history_gallerys[gid] = payback
            except Exception:
                self.log_warn("记录 payback 出错！")
            # if "status" in payback and payback["status"] == "success":
            #     self.success_gallerys_id.add()

            # 保存单个图集日志（仅供后续统计使用）
            path = "data"+os.sep + \
                payback["gallery_id"]+os.sep + \
                payback["gallery_id"]+"_page_info.json"
            with open(path, "w", encoding="utf8") as fp:
                json.dump(payback, fp)
            self.log_info("页面信息：" + os.path.abspath(path))
            # 保存全部爬取日志

        # 备份（重命名）原有日志
        # if os.path.exists(self.history_gallerys_path):
        #     os.rename(self.history_gallerys_path, "data" + os.sep + "history_gellerys_" +
        #               datetime.now().strftime(r"%Y-%m-%d__%H.%M.%S") + ".json")

        # 重写日志
        with open("data" + os.sep + "history.json", "w") as f:
            # 重新转化成功、失败记录set为list，方便序列化
            self.history_gallerys["success_gallerys_id"] = list(
                self.success_gallerys_id)
            self.history_gallerys["failed_gallerys_id"] = list(
                self.failed_gallerys_id)
            json.dump(self.history_gallerys, f)

    def getCover(self, p):
        img = p.findChild("img")
        if "data-original" in img.attrs:
            return img.attrs["data-original"]
        elif "src" in img.attrs:
            return img.attrs["src"]
        else:
            return "[!! NO COVER !!]"

    def sleep(self, msg=None):
        if msg is None:
            self.log_Info("休眠 "+str(self.sleep_time)+"s 防止被封IP...")
        else:
            self.log_Info(msg + os.linesep + "休眠 " +
                          str(self.sleep_time)+"s 防止被封IP...")
        time.sleep(self.sleep_time)

    def init_logging(self):
        self.log = logging.Logger("mzitu_log")
        self.log_path = "log" + os.sep + "mzitu.com_" + \
            self.start_time.strftime(r"%Y-%m-%d__%H.%M.%S")+".log"
        filehandler = logging.FileHandler(
            self.log_path, mode='a', encoding="utf8")
        fmt = logging.Formatter(
            r"%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s")
        filehandler.setFormatter(fmt)
        self.log.addHandler(filehandler)
        self.log_info(">> Logging at " + os.path.abspath(self.log_path))

    def log_warn(self, msg):
        print("#"*15 + " WARNNING " + "#"*15 +
              os.linesep + str(msg) + os.linesep+"#"*40)
        self.log.warn(msg)

    def log_Info(self, msg):
        print("#"*17 + " INFO " + "#"*17 +
              os.linesep + str(msg) + os.linesep+"#"*40)
        self.log.info(msg)

    def log_info(self, msg):
        print(">> " + str(msg))
        self.log.info(msg)

    def get_gid(self, link: str):
        return re.search(r"/([0-9]+)/?", link).group(1)


if __name__ == "__main__":
    mz = MzituSpider(update=False)
    mz.debug = True
    mz.proxy = None
    # mz.loadBasic()
    # mz.loadPagesData()
    mz.beginTask()
