import sqlite3
from Wind import Wind
from TableModel import TableModel
from resource_path import get_resource_path

class ManageWind:
    
    def __init__(self):
        self.conn=sqlite3.connect(get_resource_path('wind.db'))
        self.cursor=self.conn.cursor()    
    def createWindTable(self,windListName):
        create='''
                CREATE TABLE IF NOT EXISTS {} (
                id INTEGER ,
                wind_level INTEGER PRIMARY KEY,
                wind_name TEXT,
                wind_speed FLOAT,
                wind_pressure FLOAT
                )'''.format(windListName)
        print(create)
        self.cursor.execute(create)
        self.conn.commit()
    #插入数据
    def insertWind(self,windListName,wind:Wind):
        data=(wind.level,wind.name,wind.speed,wind.pressure) 
        query='''INSERT INTO {} (
                wind_level,
                wind_name,
                wind_speed,
                wind_pressure
                ) 
                VALUES (?,?,?,?)  
            '''.format(windListName)
        
        self.cursor.execute(query,data)
        self.conn.commit()  
    #查询数据  
    def selectWind(self,windListName,wind_property,level): 
        data=(level,)
        query='''SELECT {} FROM {} WHERE wind_level=?'''.format(wind_property,windListName)
        self.cursor.execute(query,data)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        return data
    def selectAllWind(self,windListName,headers):
        query='''SELECT * FROM {}'''.format(windListName)
        self.cursor.execute(query)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        tableModel=TableModel(data,headers)
        return tableModel
    #更新数据
    def  updateWind(self,windListName,wind:Wind):
      data=(wind.name,wind.speed,wind.pressure,wind.level,)
      update='''UPDATE {} SET wind_name=?,wind_speed=?,wind_pressure=?  WHERE wind_level=?'''.format(windListName)
      self.cursor.execute(update,data)
      self.conn.commit()
    #删除数据
    def deleteWind(self,windListName,level):
        data=(level,)
        delete='''DELETE FROM {} WHERE wind_level=?'''.format(windListName)
        self.cursor.execute(delete,data)
        self.conn.commit()
       
