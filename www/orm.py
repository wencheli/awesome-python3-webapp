import aiomysql, asyncio,logging


#创建pool
@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = yield from aiomysql.create_pool(
        host = kw.get('host','localhost'),
        port = kw.get('port',3306),
        user = kw['user'],
        password = kw['password'],
        db = kw['db'],
        charset = kw.get('charset','utf-8'),
        autocommit = kw.get('autocommit',True),
        maxsize = kw.get('maxsize', 10),
        minsize = kw.get('minsize', 1),
        loop = loop
    )

#select函数
@asyncio.coroutine
def select(sql, args, size=None):
    log(sql,args)
    global __pool
    with (yield from __pool) as conn:
        cur = yield from conn.cursor(aiomysql.DictCursor)
        yield from cur.execute(sql.replace('?','%s'), args or ())
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info('rows returned: %s' % len(rs))
        return rs

#通用execute函数
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

#ORM
from orm import Model

# 定义用户数据类，在类级别上定义的属性用来描述User对象和表的映射关系，
# 而实例属性必须通过__init__()方法去初始化，所以两者互不干扰
class User(Model):
    __table__='users'

    id=IntegerField(primary_key=True)
    name=StringField()

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

    def getvalue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self,key):
        value = getattr(self,key,None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' %s (key, str(value)))
                setattr(self,key,value)
        return value

    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        ' find object by primary key. '
        rs = yield from select('%s where '%s'=?' % (cls.__select__,cls.__primary_key__),[pk],1)
        if len(rs)==0:
            return None
        return cls(**rs[0])

    @asyncio.coroutine
    def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows=yield from execute(self.__insert__,args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)

#class Field 定义

class Field(object):

    def __init__(self,name,column_type,primary_key,default):
        self.name=name
        self.column_type=column_type
        self.primary_key =primary_key
        self.default = default
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.primary_key)

class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name,ddl,primary_key,default)

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
                    #找到主键
                    if primarykey:
                        raise RuntimeError('Dumplicate primary key for field: %s' % k)
                    primarykey=k
                else:
                    fields.append(k)
        if not primarykey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields =list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__']=mappings #保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primarykey #主键属性名
        attrs['__field__'] = fields  #除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, `%s` from `%s`' % (primarykey, ', '.join(escaped_fields),tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields),
                                primarykey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?'
                                % (mappings.get(f).name or f),fields)),primarykey)

        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName,primarykey)
        return type.__new__(cls,name,bases,attrs)
