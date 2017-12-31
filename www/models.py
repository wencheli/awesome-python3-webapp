# -*- coding: utf-8 -*-

import time, uuid, sys

from orm import Model, StringField, BooleanField, FloatField, TextField

def next_id():
    return '%015d%s000' % (int(time.time() * 1000), uuid.uuid4().hex)

# 定义用户数据类，在类级别上定义的属性用来描述User对象和表的映射关系，
# 而实例属性必须通过__init__()方法去初始化，所以两者互不干扰
class User(Model):
    __table__='users'

    #定义属性的类型和默认参数！这些参数会传入metaclass来生成User类
    id = StringField(primary_key=True,default=next_id, ddl='varchar(50)')
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name= StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(default=time.time)

class Blog(Model):
    __table__='blogs'

    id=StringField(primary_key=True,default=next_id, ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    name= StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(200)')
    content = TextField()
    created_at = FloatField(default=time.time)

class Comment(Model):
    __table__='comments'

    id=StringField(primary_key=True,default=next_id, ddl='varchar(50)')
    blog_id = StringField(ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)

#测试数据库是否正常工作
'''
import orm, asyncio
from models import User, Blog, Comment

def test(loop):
    yield from orm.create_pool(loop = loop, user='www-data', password='www-data', db='awesome')

    u = User(name='Test55', email='test66@qq.com', passwd='1234567890', image='about:blank')

    yield from u.save()
    yield from orm.destroy_pool()



if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test(loop))
    loop.close()
'''