import sqlite3
from Film import Film
from TableModel import TableModel
from resource_path import get_resource_path

class ManageFilm:
    
    def __init__(self):
        self.conn=sqlite3.connect(get_resource_path('Film.db'))
        self.cursor=self.conn.cursor()    
    def createFilmTable(self,filmListName):
        create='''
                CREATE TABLE IF NOT EXISTS {} (
                id INTEGER PRIMARY KEY,
                manufacture TEXT,
                material TEXT,
                thickness FLOAT,
                unitWeight FLOAT,
                breakingForceWarp FLOAT,
                breakingForceWeft FLOAT,
                tearStrengthWarp FLOAT,
                tearStrengthWeft FLOAT,
                peelStrengthWarp FLOAT,
                peelStrengthWeft FLOAT,
                elongateWarp FLOAT,
                elongateWeft FLOAT,
                permeability FLOAT
                )'''.format(filmListName)
        print(create)
        self.cursor.execute(create)
        self.conn.commit()
    #插入数据
    def insertFilm(self,filmListName,film:Film):
        data=(film.manufacture,
              film.material,
              film.thickness,
              film.unitWeight,
              film.breakingForceWarp,film.breakingForceWeft,
              film.tearStrengthWarp,film.tearStrengthWeft,
              film.peelStrengthWarp,film.peelStrengthWeft,
              film.elongateWarp,film.elongateWeft,film.permeability) 
        query='''INSERT INTO {} (
                manufacture,
                material,
                thickness,
                unitWeight,
                breakingForceWarp,
                breakingForceWeft,
                tearStrengthWarp,
                tearStrengthWeft,
                peelStrengthWarp,
                peelStrengthWeft,
                elongateWarp,
                elongateWeft,
                permeability
                ) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)  
            '''.format(filmListName)
        
        self.cursor.execute(query,data)
        self.conn.commit()  
    #查询数据  
    def selectFilm(self,filmListName,film_property,manufacture,material,thickness): 
        data=(manufacture,material,thickness,)
        query='''SELECT {} FROM {} WHERE manufacture=? AND material=? AND thickness=?'''.format(film_property,filmListName)
        self.cursor.execute(query,data)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        return data
    def selectAllFilm(self,filmListName,headers):
        query='''SELECT * FROM {}'''.format(filmListName)
        self.cursor.execute(query)
        values=self.cursor.fetchall()
        data=[list(row) for row in values]
        tableModel=TableModel(data,headers)
        return tableModel
    #更新数据
    def  updateFilm(self,filmListName,film:Film):
      data=(film.unitWeight,film.breakingForceWarp,film.breakingForceWeft,
              film.tearStrengthWarp,film.tearStrengthWeft,
              film.peelStrengthWarp,film.peelStrengthWeft,
              film.elongateWarp,film.elongateWeft,film.permeability,film.manufacture,film.material,film.thickness)
      update='''UPDATE {} SET unitWeight=?,
      breakingForceWarp=?,
      breakingForceWeft=?,
      tearStrengthWarp=?,
      tearStrengthWeft=?,
      peelStrengthWarp=?,
      peelStrengthWeft=?,
      elongateWarp=?,
      elongateWeft=?,
      permeability=?
      WHERE manufacture=? AND material=? AND thickness=?'''.format(filmListName)
      self.cursor.execute(update,data)
      self.conn.commit()
    #删除数据
    def deleteFilm(self,filmListName,manufacture,material,thickness):
        data=(manufacture,material,thickness,)
        delete='''DELETE FROM {} WHERE manufacture=? AND material=? AND thickness=?'''.format(filmListName)
        self.cursor.execute(delete,data)
        self.conn.commit()
       
