import sqlite3
from Tube import Tube
from TableModel import TableModel
from resource_path import get_resource_path

class ManageTube:
    
    def __init__(self):
        self.conn=sqlite3.connect(get_resource_path('Tube.db'))
        self.cursor=self.conn.cursor()    
    def createTubeTable(self,tubeListName):
        create='''
                CREATE TABLE IF NOT EXISTS {} (
                id INTEGER PRIMARY KEY ,
                material TEXT,
                diameter FLOAT,
                thickness FLOAT,
                unitWeight FLOAT
                )'''.format(tubeListName)
        print(create)
        self.cursor.execute(create)
        self.conn.commit()
    #插入数据
    def insertTube(self,tubeListName,tube:Tube):
        data=(tube.material,tube.diameter,tube.thickness,tube.unitWeight) 
        query='''INSERT INTO {} (
                material,
                diameter,
                thickness,
                unitWeight
                ) 
                VALUES (?,?,?,?)  
            '''.format(tubeListName)       
        self.cursor.execute(query,data)
        self.conn.commit()  
    #查询数据  
    def selectTube(self,tubeListName,tube_property,material,diameter,thickness): 
        data=(material,diameter,thickness,)
        query='''SELECT {} FROM {} WHERE material=? AND diameter=? AND thickness=?'''.format(tube_property,tubeListName)
        self.cursor.execute(query,data)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        return data
    def selectAllTube(self,tubeListName,headers):
        query='''SELECT * FROM {}'''.format(tubeListName)
        self.cursor.execute(query)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        tableModel=TableModel(data,headers)
        return tableModel
    #更新数据
    def  updateTube(self,tubeListName,tube:Tube):
      data=(tube.unitWeight,tube.material,tube.diameter,tube.thickness)
      update='''UPDATE {} SET unitWeight=??  WHERE material=? AND diameter=? AND thickness=?'''.format(tubeListName)
      self.cursor.execute(update,data)
      self.conn.commit()
    #删除数据
    def deleteTube(self,tubeListName,material,diameter,thickness):
        data=(material,diameter,thickness,)
        delete='''DELETE FROM {} WHERE material=? AND diameter=? AND thickness=?'''.format(tubeListName)
        self.cursor.execute(delete,data)
        self.conn.commit()
       
