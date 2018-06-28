from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, PickleType
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_json import NestedMutableJson, MutableJson


Base = declarative_base()

class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(Integer, primary_key=True, unique=True)
    message = Column(String(2000))
    channel = Column(BigInteger)
    time = Column(Integer)
    interval = Column(Integer)

    def __repr__(self):
        return '<Reminder "{}" <#{}> {}s>'.format(self.message, self.channel, self.time)


class Server(Base):
    __tablename__ = 'servers'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    prefix = Column( String(5) )
    language = Column( String(2) )
    timezone = Column( String(30) )
    blacklist = Column( NestedMutableJson )
    restrictions = Column( NestedMutableJson )
    tags = Column( MutableJson )
    autoclears = Column( MutableJson )

    def __repr__(self):
        return '<Server {}>'.format(self.id)


engine = create_engine('mysql+pymysql://jude:d8c1F\'T^!$K+6Xy979~Gx9hLwfU;@ssh.jellywx.co.uk/test')
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()