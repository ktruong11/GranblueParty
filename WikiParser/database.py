#!/usr/bin/python3

import datetime
import getopt
import os
import sys

import psycopg2

from config import dbconfig
from config import defines

class Col:
  def __init__(self, name, datatype, primary = False, updateOnInsert = True):
    self.name = name.lower()
    self.datatype = datatype
    self.primary = primary
    self.updateOnInsert = updateOnInsert

class Table:
  def __init__(self, name, cols, constraint = "", conflictCondition = ""):
    self.name = name
    self.cols = cols
    self.constraint = constraint
    self.copy = True
    self.constArray = None
    self.constDict = None
    self.updateOnConflict = False
    self.conflictCondition = conflictCondition
    self.dropBeforeUpdate = False
    self.dontUpdate = False
  
  def setDoNotCopy(self):
    self.copy = False
    return self

  def setConstArray(self, constArray):
    self.constArray = constArray
    return self

  def setConstDict(self, constDict):
    self.constDict = constDict
    return self

  def setUpdateOnConflict(self):
    self.updateOnConflict = True
    return self

  def setDropBeforeUpdate(self):
    self.dropBeforeUpdate = True
    return self

  def setDoNotUpdate(self):
    self.dontUpdate = True
    return self

  # Create the Table
  def create(self):
    colsListStr, primaryCols = self.getCols(True)
    constraint = ""
    if len(self.constraint) > 0:
      constraint = ", " + self.constraint      
    q = 'CREATE TABLE IF NOT EXISTS ' + self.name + ' (' + colsListStr + ', PRIMARY KEY (' + primaryCols + ') ' + constraint + ');'
    dbconfig.getCursor().execute(q)

    # Add missing columns
    dbconfig.getCursor().execute('SELECT * FROM ' + self.name + ' LIMIT 0;')
    colNames = [desc[0] for desc in dbconfig.getCursor().description]
    for c in self.cols:
      if not c.name in colNames:
        dbconfig.getCursor().execute('ALTER TABLE ' + self.name + ' ADD COLUMN ' + c.name + ' ' + c.datatype + ';')
        print("Adding column " + c.name + " to table " + self.name)

    if self.constArray:
      # Static data, create from the array
      colsListStr, _ = self.getCols(False)
      for idx, val in enumerate(self.constArray):
        dbconfig.getCursor().execute('INSERT INTO ' + self.name + '(' + colsListStr + ') VALUES (%s, %s) ON CONFLICT DO NOTHING;', (idx, val))
    elif self.constDict:
      colsListStr, _ = self.getCols(False)
      for val, idx in self.constDict.items():
        dbconfig.getCursor().execute('INSERT INTO ' + self.name + '(' + colsListStr + ') VALUES (%s, %s) ON CONFLICT DO NOTHING;', (idx, val))

  # Dump the Table to a file
  def dump(self):
    if self.copy:
      output = open(os.path.join('db', self.name + '.csv'), 'w', encoding='utf8')
      
      # Order by all columns, in order
      orderByClause = ''
      for col in self.cols:
        if col.datatype.startswith('JSON'):
          continue
        if len(orderByClause) > 0:
          orderByClause += ', '
        orderByClause += col.name

      dbconfig.getCursor().copy_expert('COPY (SELECT * FROM ' + self.name + ' ORDER BY ' + orderByClause + ') TO STDOUT;', output)
      output.close()
  
  def drop(self):
    if self.dropBeforeUpdate:
      # Table must exist (else, we forget to create the tables...)
      dbconfig.getCursor().execute('DROP TABLE ' + self.name + ';')

  # Update Table from a CSV file
  def update(self):
    # Don't update static data Tables
    if self.dontUpdate:
      return

    if self.dropBeforeUpdate:
      self.create()

    # Copy from an existing CSV file
    dbconfig.getCursor().execute('CREATE TEMP TABLE tmp_table (LIKE ' + self.name + ');')
    input = open(os.path.join('db', self.name + '.csv'), 'r', encoding='utf8')
    dbconfig.getCursor().copy_from(input, 'tmp_table')
    dbconfig.getCursor().execute('INSERT INTO ' + self.name + ' SELECT * FROM tmp_table ON CONFLICT ' + self.getConflit(onUpdate=True) +  ';')
    dbconfig.getCursor().execute('DROP TABLE tmp_table;')

  # Update the value of a single row
  def updateValue(self, primaryKey, keyId, rowToUpdate, value):
    dbconfig.getCursor().execute('UPDATE ' + self.name + ' SET ' + rowToUpdate + '= %s WHERE ' + primaryKey + '= %s;', [value, keyId])

  def insert(self, values, returning=""):
    if self.dropBeforeUpdate:
      self.create()
    
    if len(returning) > 0:
      returning = " RETURNING " + returning

    # Don't use len(values) for %s to make sure the number of colums is the same
    colsList, _ = self.getCols(False)
    query = 'INSERT INTO ' + self.name + '(' + colsList + ') VALUES (' + self.getPercentS() + ') ON CONFLICT ' + self.getConflit(onUpdate=False) + returning + ';'
    for val in values:
      dbconfig.getCursor().execute(query, val)

    if len(returning) > 0:
      return dbconfig.getCursor().fetchone()[0]

  def getCount(self):
    dbconfig.getCursor().execute('SELECT COUNT(*) FROM ' + self.name + ';')
    return dbconfig.getCursor().fetchone()[0]

  # Helper methods
  def getCols(self, withDatatype):
    colsList = ""
    primaryCols = ""
    for col in self.cols:
      if len(colsList) > 0:
        colsList += ', '
      colsList += col.name
      if withDatatype:
        colsList += ' ' + col.datatype

      if col.primary:
        if len(primaryCols) > 0:
          primaryCols += ', '
        primaryCols += col.name
    
    return colsList, primaryCols
  
  def getNonPrimaryCols(self, onUpdate):
    colsList = ""
    excludedCols = ""
    for col in self.cols:
      if not col.primary and (col.updateOnInsert or onUpdate):
        if len(colsList) > 0:
          colsList += ', '
          excludedCols += ', '

        colsList += col.name
        excludedCols += 'Excluded.' + col.name
    
    return colsList, excludedCols

  def getConflit(self, onUpdate):
    if self.updateOnConflict:
      _, primaryCols = self.getCols(True)
      if len(self.conflictCondition) > 0:
        primaryCols = self.conflictCondition

      colsList, excludedCols = self.getNonPrimaryCols(onUpdate)
      return '(' + primaryCols + ') DO UPDATE SET (' + colsList + ') = (' + excludedCols + ')'
    else:
      return 'DO NOTHING'

  def getPercentS(self):
    string = ""
    for _ in self.cols:
      if len(string) > 0:
        string += ', '
      string += '%s'
    return string

# Static data
all_tables = [
  Table('Rarity',
        [ Col('rarityId', 'INT NOT NULL', True),
          Col('rarityName', 'TEXT UNIQUE NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setConstArray(defines.RARITIES),
  Table('Element',
        [ Col('elementId', 'INT NOT NULL', True),
          Col('elementName', 'TEXT UNIQUE NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setConstArray(defines.ELEMENTS),
  Table('CharacterType',
        [ Col('characterTypeId', 'INT NOT NULL', True),
          Col('characterTypeName', 'TEXT UNIQUE NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setConstArray(defines.CHARATYPES),
  Table('Race',
        [ Col('raceId', 'INT NOT NULL', True),
          Col('raceName', 'TEXT UNIQUE NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setConstArray(defines.RACES),
  Table('WeaponType',
        [ Col('weaponTypeId', 'INT NOT NULL', True),
          Col('weaponTypeName', 'TEXT UNIQUE NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setConstArray(defines.WEAPONTYPES),
  Table('DrawType',
        [ Col('drawTypeId', 'INT NOT NULL', True),
          Col('drawTypeName', 'TEXT UNIQUE NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setConstDict(defines.OBTAIN),
  # Stable, update
  Table('Character',
        [ Col('characterId', 'INT NOT NULL', True),
          Col('nameEn', 'TEXT NOT NULL'),
          Col('nameJp', 'TEXT NOT NULL'),
          Col('starsBase', 'INT NOT NULL'),
          Col('starsMax', 'INT NOT NULL'),
          Col('rarityId', 'INT NOT NULL REFERENCES Rarity(rarityId)'),
          Col('elementId', 'INT NOT NULL REFERENCES Element(elementId)'),
          Col('characterTypeId', 'INT NOT NULL REFERENCES CharacterType(characterTypeId)'),
          Col('raceId', 'INT NOT NULL REFERENCES Race(raceId)'),
          Col('drawTypeId', 'INT REFERENCES DrawType(drawTypeId)'),
          Col('releaseDate', 'DATE'),
          Col('atkMLB', 'INT'),
          Col('atkFLB', 'INT'),
          Col('hpMLB', 'INT'),
          Col('hpFLB', 'INT'),
        ])
        .setUpdateOnConflict(),
  Table('Summon',
        [ Col('summonId', 'INT NOT NULL', True),
          Col('nameEn', 'TEXT NOT NULL'),
          Col('nameJp', 'TEXT NOT NULL'),
          Col('starsBase', 'INT NOT NULL'),
          Col('starsMax', 'INT NOT NULL'),
          Col('rarityId', 'INT NOT NULL REFERENCES Rarity(rarityId)'),
          Col('elementId', 'INT NOT NULL REFERENCES Element(elementId)'),
          Col('drawTypeId', 'INT REFERENCES DrawType(drawTypeId)'),
          Col('releaseDate', 'DATE'),
          Col('atk', 'INT'),
          Col('atkMLB', 'INT'),
          Col('atkFLB', 'INT'),
          Col('atkULB', 'INT'),
          Col('hp', 'INT'),
          Col('hpMLB', 'INT'),
          Col('hpFLB', 'INT'),
          Col('hpULB', 'INT'),
          Col('data', 'JSON', updateOnInsert=False)
        ])
        .setUpdateOnConflict(),
  Table('Weapon',
        [ Col('weaponId', 'INT NOT NULL', True),
          Col('nameEn', 'TEXT NOT NULL'),
          Col('nameJp', 'TEXT NOT NULL'),
          Col('starsBase', 'INT NOT NULL'),
          Col('starsMax', 'INT NOT NULL'),
          Col('rarityId', 'INT NOT NULL REFERENCES Rarity(rarityId)'),
          Col('elementId', 'INT NOT NULL REFERENCES Element(elementId)'),
          Col('weaponTypeId', 'INT NOT NULL REFERENCES WeaponType(weaponTypeId)'),
          Col('atk', 'INT'),
          Col('atkMLB', 'INT'),
          Col('atkFLB', 'INT'),
          Col('atkULB', 'INT'),
          Col('hp', 'INT'),
          Col('hpMLB', 'INT'),
          Col('hpFLB', 'INT'),
          Col('hpULB', 'INT')
        ])
        .setUpdateOnConflict(),
  Table('Weapon_SkillData',
        [ Col('skilldataId', 'INT NOT NULL', True),
          Col('icon', 'TEXT NOT NULL'),
          Col('skillName', 'TEXT NOT NULL'),
          Col('data', 'JSON', updateOnInsert=False)
        ],
        constraint="UNIQUE(icon, skillName)",
        conflictCondition="icon, skillName")
        .setUpdateOnConflict(),
  Table('Weapon_Skill',
        [ Col('weaponId', 'INT NOT NULL REFERENCES Weapon(weaponId)', True),
          Col('slot', 'INT NOT NULL', True),
          Col('level', 'INT NOT NULL', True),
          Col('keyId', 'INT'),
          Col('skilldataId', 'INT NOT NULL REFERENCES Weapon_SkillData(skilldataId)')          
        ])
        .setUpdateOnConflict(),
  # Clear
  Table('Class',
        [ Col('classId', 'INT NOT NULL', True),
          Col('nameEn', 'TEXT NOT NULL'),
          Col('row', 'INT NOT NULL'),
          Col('family', 'INT NOT NULL')
        ])
        .setDropBeforeUpdate(),
  Table('WeaponSpecialty',
        [ Col('characterId', 'INT REFERENCES Character(characterId)', True),
          Col('weaponTypeId', 'INT REFERENCES WeaponType(weaponTypeId)', True)
        ])
        .setDropBeforeUpdate(),
  Table('CharacterSkill',
        [ Col('characterId', 'INT REFERENCES Character(characterId)', True),
          Col('characterSkillOrder', 'INT NOT NULL', True),
          Col('characterSkillName', 'TEXT NOT NULL'),
          Col('characterSkillObtain', 'INT')
        ])
        .setDropBeforeUpdate(),
  Table('ClassSkill',
        [ Col('skillId', 'INT NOT NULL', True),
          Col('nameEn', 'TEXT NOT NULL'),
          Col('family', 'INT'),
          Col('exMastery', 'BOOLEAN NOT NULL')
        ])
        .setDropBeforeUpdate(),
  Table('Class_ClassSkill',
        [ Col('classId', 'INT NOT NULL REFERENCES Class(classId)', True),
          Col('skillId', 'INT NOT NULL REFERENCES ClassSkill(skillId)', True),
          Col('index', 'INT NOT NULL')
        ])
        .setDropBeforeUpdate(),
  Table('Skin_Character',
        [ Col('skinId', 'INT NOT NULL', True),
          Col('characterId', 'INT REFERENCES Character(characterId)', True)
        ])
        .setDropBeforeUpdate(),      
  # Protected
  Table('UserAccount',
        [ Col('userid', 'SERIAL', True), # This column should be ignored by the iterators of class Table, but since the functions are not used for this table, it's Ok
          Col('username', 'TEXT UNIQUE NOT NULL'),
          Col('password', 'TEXT NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate(),
  Table('UserCollectionCharacter',
        [ Col('userid', 'INT NOT NULL REFERENCES UserAccount(userid)', True),
          Col('characterId', 'INT NOT NULL REFERENCES Character(characterId)', True),
          Col('stars', 'INT'),
          Col('owned', 'BOOLEAN NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate(),
  Table('UserCollectionSummon',
        [ Col('userid', 'INT NOT NULL REFERENCES UserAccount(userid)', True),
          Col('summonId', 'INT NOT NULL REFERENCES Summon(summonId)', True),
          Col('stars', 'INT'),
          Col('owned', 'BOOLEAN NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate(),
  Table('Party',
        [ Col('partyId', 'SERIAL', True),
          Col('userId', 'INT NOT NULL REFERENCES UserAccount(userid)'),
          Col('partyName', 'TEXT'),
          Col('partyData', 'JSON NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate(),
  Table('Daily',
        [ Col('userId', 'INT NOT NULL REFERENCES UserAccount(userid)', True),
          Col('dailyData', 'JSON NOT NULL')
        ])
        .setDoNotCopy()
        .setDoNotUpdate(),
  Table('SummonAura',
        [ Col('summonId', 'INT NOT NULL REFERENCES Summon(summonId)', True),
          Col('aura', 'TEXT'),
          Col('auraMLB', 'TEXT'),
          Col('auraFLB', 'TEXT'),
          Col('auraULB', 'TEXT'),
          Col('subaura', 'TEXT'),
          Col('subauraMLB', 'TEXT'),
          Col('subauraFLB', 'TEXT'),
          Col('subauraULB', 'TEXT'),
          Col('ignore', 'BOOLEAN DEFAULT False', updateOnInsert=False)
        ])
        .setDoNotCopy()
        .setDoNotUpdate()
        .setUpdateOnConflict(),
]

dico_tables = {}
for t in all_tables:
  dico_tables[t.name] = t

def printHelp():
  print('--create: Create tables')
  print('--dump:   Dump tables to CSV files')
  print('--update: Update DB from CSV files')
  sys.exit(1)

def main(argv):
  try:
    opts, args = getopt.getopt(argv, '', ['create', 'dump', 'update'])
  except getopt.GetoptError:
    printHelp()
  if len(argv) == 0 or len(args) > 0 or len(opts) != 1:
    printHelp()

  for opt, _ in opts:
    if opt == '--create':
      # Table migration
      dbconfig.getCursor().execute('DROP TABLE IF EXISTS weaponskill_weapon;')
      dbconfig.getCursor().execute('DROP TABLE IF EXISTS weaponskill;')

      for i in all_tables:
        i.create()

    elif opt == '--dump':
      for i in all_tables:
        i.dump()

    elif opt == '--update':
      for i in reversed(all_tables):
        i.drop()
      for i in all_tables:
        i.update()
      
      # Delete bad rows
      dbconfig.getCursor().execute('DELETE FROM summonaura WHERE summonid = 2040199;')
      dbconfig.getCursor().execute('DELETE FROM summonaura WHERE summonid = 2030017;')
      dbconfig.getCursor().execute('DELETE FROM summon WHERE summonid = 2040199;')
      dbconfig.getCursor().execute('DELETE FROM summon WHERE summonid = 2030017;')
      
      output = open(os.path.join('..', 'db.version'), 'w', encoding='utf8')
      output.write(str(datetime.datetime.now()))
      output.close()

if __name__ == '__main__':
  main(sys.argv[1:])