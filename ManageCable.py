import sqlite3
from Cable import Cable
from TableModel import TableModel
from resource_path import get_resource_path
from aerostat_physics import KGF_PER_KN

class ManageCable:
    
    def __init__(self):
        self.conn=sqlite3.connect(get_resource_path('Cable.db'))
        self.cursor=self.conn.cursor()    
    def createCableTable(self,cableListName):
        create='''
                CREATE TABLE IF NOT EXISTS {} (
                id INTEGER PRIMARY KEY ,
                material TEXT,
                diameter FLOAT,
                unitWeight FLOAT,
                breakingForce FLOAT
                )'''.format(cableListName)
        print(create)
        self.cursor.execute(create)
        self.conn.commit()
    #插入数据
    def insertCable(self,cableListName,cable:Cable):
        data=(cable.material,cable.diameter,cable.unitWeight,cable.breakingForce/KGF_PER_KN) 
        query='''INSERT INTO {} (
                material,
                diameter,
                unitWeight,
                breakingForce
                ) 
                VALUES (?,?,?,?)  
            '''.format(cableListName)
        
        self.cursor.execute(query,data)
        self.conn.commit()  
    #查询数据  
    def selectCable(self,cableListName,cable_property,material,diameter): 
        data=(material,diameter,)
        query='''SELECT {} FROM {} WHERE material=? AND diameter=?'''.format(cable_property,cableListName)
        self.cursor.execute(query,data)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        if cable_property=='*':
            for row in data:
                if row[4] is not None:
                    row[4]=round(row[4]*KGF_PER_KN,1)
        return data
    def selectAllCable(self,cableListName,headers):
        query='''SELECT * FROM {}'''.format(cableListName)
        self.cursor.execute(query)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        for row in data:
            if row[4] is not None:
                row[4]=round(row[4]*KGF_PER_KN,1)
        tableModel=TableModel(data,headers)
        return tableModel
    #更新数据
    def  updateCable(self,cableListName,cable:Cable):
      data=(cable.unitWeight,cable.breakingForce/KGF_PER_KN,cable.material,cable.diameter,)
      update='''UPDATE {} SET unitWeight=?,breakingForce=?  WHERE material=? AND diameter=?'''.format(cableListName)
      self.cursor.execute(update,data)
      self.conn.commit()
    #删除数据
    def deleteCable(self,cableListName,material,diameter):
        data=(material,diameter,)
        delete='''DELETE FROM {} WHERE material=? AND diameter=?'''.format(cableListName)
        self.cursor.execute(delete,data)
        self.conn.commit()
       
