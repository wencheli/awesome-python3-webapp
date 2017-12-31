# -*- coding: utf-8 -*-

import aiomysql, asyncio,logging

def log(sql, args=()):
    logging.info('SQL: %s' % sql)

#创建pool
@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    # 全局变量,如果在函数内部修改外部变量,需声明为全局变量
    global __pool
    __pool = yield from aiomysql.create_pool(
        host = kw.get('host','localhost'),
        port = kw.get('port',3306),
        user = kw['user'],
        password = kw['password'],
        db = kw['db'],
        charset = kw.get('charset','utf8'),
        autocommit = kw.get('autocommit',True),
        maxsize = kw.get('maxsize', 10),
        minsize = kw.get('minsize', 1),
        loop = loop
    )

#查看数据库数据的函数(第一个参数为sql语句,第二个则是占位符对应的参数)
async def select(sql, args, size=None):
    log(sql,args)
    global __pool
    async with __pool.get() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # mysql使用%s作为占位符,sql使用的是?作为占位符,使用replace()函数替换掉,
            # 后面就是占位符对应的参数,这里巧妙的使用了or关键字的短路原理,左为真返回左,否则返回or右边的
            await cur.execute(sql.replace('?','%s'), args or ())
            if size:
                #fetchmany()方法可以获得多条数据，但需要指定数据的条数
                # 一次性返回size条查询结果，结果是一个list，里面是tuple
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()
        # 关闭游标，不用手动关闭conn，因为是在with语句里面，会自动关闭，因为是select，所以不需要提交事务(commit)
        logging.info('rows returned: %s' % len(rs))
        return rs

#通用execute函数，update/save/remove使用
@asyncio.coroutine
def execute(sql, args):
    log(sql)
    with (yield from __pool) as conn:
        try:
            cur = yield from conn.cursor()
            yield from cur.execute(sql.replace('?','%s'), args)
            affected = cur.rowcount
            yield from cur.close()
        except BaseException as e:
            raise
        return affected

# 这个函数主要是把查询字段计数并替换成sql识别的?占位符，后面通过传入参数来实现增、删、查、改
# 比如说：insert into  `User` (`password`, `email`, `name`, `id`) values (?,?,?,?)  看到了么 后面这四个问号
def create_args_string(num):
    L=[]
    for n in range(num):
        L.append('?')
    return ', '.join(L)

#ORM

class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        #排除Model类本身
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        #获取table名称
        tableName=attrs.get('__table__',None) or name
        logging.info('found model: %s table: %s' % (name, tableName))
        #获取所有的Field和主键名
        mappings=dict()
        fields=[]
        primarykey=None
        # 注意这里attrs的key是字段名，value是字段实例，不是字段的具体值
        # 比如User类的id=StringField(...) 这个value就是这个StringField的一个实例，而不是实例化
        # 的时候传进去的具体id值
        for k,v in attrs.items():
            if isinstance(v,Field):
                logging.info('  found mapping: %s ==> %s' % (k,v))
                mappings[k]=v
                if v.primary_key:
                    # 一个表只能有一个主键，当再出现一个主键的时候就报错
                    if primarykey:
                        raise RuntimeError('Dumplicate primary key for field: %s' % k)
                    primarykey=k
                else:
                    fields.append(k)
        # 如果主键不存在也将会报错，在这个表中没有找到主键，一个表只能有一个主键，而且必须有一个主键
        if not primarykey:
            raise RuntimeError('Primary key not found.')

        # 为了防止创建出的类实例属性与类属性冲突，所以将其去掉， user=User(id='10001')，实例和类属性都有id是独立的！
        # attrs[k]里面保存的是类属性，按说后面赋值时，会拿实例属性会覆盖掉它，但是...并没有！所以去除掉类属性
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields =list(map(lambda f: '`%s`' % f, fields))
        #attrs[]是创建类的属性或者方法:
        attrs['__mappings__']=mappings #保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primarykey #主键属性名
        attrs['__fields__'] = fields  #除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primarykey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields),
                                primarykey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?'
                                % (mappings.get(f).name or f),fields)),primarykey)

        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName,primarykey)
        return type.__new__(cls,name,bases,attrs)


class Model(dict, metaclass = ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has not attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self,key):
        #getattr是标准库内置函数
        value = getattr(self,key,None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self,key,value)
        return value

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        ' find objects by where clause. '
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        # 返回的rs是一个元素是tuple的list
        # **r 是关键字参数，构成了一个cls类的列表，其实就是每一条记录对应的类实例
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        ' find number by select and where. '
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        # 取出符合条件的结果加入到_num_属性中，并返回
        # 但是这个方法是要获取数据库中某一列的数目，那应该用select count才对，应该把sql语句改成如下：
        # sql = ['select count(%s) _num_ from `%s`' % (selectField, cls.__table__)]
        return rs[0]['_num_']




    @classmethod
    async def find(cls, pk):
        #find object by primary key, 最后的1是返回的个数， rs是一个list，里面是一个dict
        rs = await select('%s where `%s`=?' % (cls.__select__,cls.__primary_key__),[pk], 1)
        if len(rs)==0:
            return None
        #rs是一个列表，rs中的每个元素是一个字典，每个字典就是所查询的表中的一个条目的所有信息。
        return cls(**rs[0]) #返回一条记录，以dict的形式返回，因为cls的父类继承了dict类，** 是用来解包dict的

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows= await execute(self.__insert__,args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)
    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
#class Field 定义

class Field(object):

    def __init__(self,name,column_type,primary_key,default):
        self.name=name
        self.column_type=column_type
        self.primary_key =primary_key
        self.default = default

    #这个__str__你可以理解为这个类的注释说明,在廖雪峰的定制类一篇有详细说明
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.primary_key)

class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name,ddl,primary_key,default)

class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name,'real',primary_key,default)

class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name,'text',False,default)

@asyncio.coroutine
def destroy_pool():
    global __pool
    if __pool is not None:
        __pool.close()
        yield from __pool.wait_closed()


