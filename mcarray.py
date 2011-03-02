# methods which manipulate arrays and their elements
import os
import numpy
import multinumpy
from pymclevel import mclevel, materials
from itertools import product

# level constants
chunkWidthPow = 4
chunkWidth = pow(2,chunkWidthPow)
chunkHeight = 128
# constants
sealevel = 64
# headroom is the room between the tallest peak and the ceiling
headroom = 10
maxelev = chunkHeight-headroom-sealevel

def createArrays(minX, minZ, maxX, maxZ):
    "Create shared arrays."
    global arrayBlocks, arrayData
    minXchunk = (minX >> chunkWidthPow)
    minZchunk = (minZ >> chunkWidthPow)
    maxXchunk = (maxX >> chunkWidthPow)
    maxZchunk = (maxZ >> chunkWidthPow)
    chunkX = xrange(minXchunk-1, maxXchunk+2)
    chunkZ = xrange(minZchunk-1, maxZchunk+2)
    for x, z in product(chunkX, chunkZ):
        arrayKey = '%dx%d' % (x, z)
        arrayBlocks[arrayKey] = multinumpy.SharedMemArray(numpy.zeros((chunkWidth,chunkWidth,chunkHeight),dtype=numpy.uint8))
        arrayData[arrayKey] = multinumpy.SharedMemArray(numpy.zeros((chunkWidth,chunkWidth,chunkHeight),dtype=numpy.uint8))

def saveArrays(arraydir, maxX, minX):
    "Save shared arrays."
    maxcz = (maxX-minX) >> chunkWidthPow
    # make arraydir
    if os.path.exists(arraydir):
        [ os.remove(os.path.join(arraydir,name)) for name in os.listdir(arraydir) ]
    else:
        os.makedirs(arraydir)
    # FIXME: not-parallelizable-yet
    # modularize later
    # for each pair of shared memory arrays
    for key in arrayBlocks.keys():
        ctuple = key.split('x')
        ocx = int(ctuple[0])
        ocz = int(ctuple[1])
        cz = maxcz-ocx
        cx = ocz
        myBlocks = arrayBlocks[key].asarray()
        myData = arrayData[key].asarray()
        # save them to a file
        outfile = os.path.join(arraydir, '%dx%d.npz' % (cx, cz))
        numpy.savez(outfile, blocks=myBlocks, data=myData)

def loadArrays(world, arraydir):
    "Load all arrays from array directory."
    numarrays = 0
    # FIXME: do in parallel if possible
    for name in os.listdir(arraydir):
        numarrays += 1
        # extract arrays from file
        arrayData = numpy.load(os.path.join(arraydir,name))
        myBlocks = arrayData['blocks']
        myData = arrayData['data']
        # extract key from filename
        key = name.split('.')[0]
        ctuple = key.split('x')
        cx = int(ctuple[0])
        cz = int(ctuple[1])
        try:
            world.getChunk(cx, cz)
        except mclevel.ChunkNotPresent:
            world.createChunk(cx, cz)
        chunk = world.getChunk(cx, cz)
        for x, z in product(xrange(chunkWidth), xrange(chunkWidth)):
            chunk.Blocks[x,z] = myBlocks[chunkWidth-1-z,x]
            chunk.Data[x,z] = myData[chunkWidth-1-z,x]
        chunk.chunkChanged()
    print '%d arrays loaded' % numarrays

# each column consists of [x, z, elevval, ...]
# where ... is a block followed by zero or more number-block pairs
# examples:
# [x, y, elevval, 'Stone']
#  - fill everything from 0 to elevval with stone
# [x, y, elevval, 'Dirt', 2, 'Water']
#  - elevval down two levels of water, rest dirt
# [x, y, elevval, 'Stone', 1, 'Dirt', 1, 'Water']
#  - elevval down one level of water, then one level of dirt, then stone
# We add the final values here so the hard floor is 'Bedrock'.
def layers(columns):
    blocks = []
    for column in columns:
        x = column.pop(0)
        z = column.pop(0)
        elevval = column.pop(0)
        top = sealevel+elevval
        # overstone = sum([elem for elem in column if type(elem) == int])
        # column.insert(0, 'Bedrock')
        # column.insert(1, top-overstone-1)
        # column.insert(2, 'Stone')
        column.insert(0, 'Stone')
        while (len(column) > 0 or top > 0):
            # better be a block
            block = column.pop()
            if (len(column) > 0):
                layer = column.pop()
            else:
                layer = top
            # now do something
            if (layer > 0):
                [blocks.append((x, y, z, block)) for y in xrange(top-layer,top)]
                top -= layer
    setBlocksAt(blocks)
        
# fillBlocks(right, length, bottom, height, back, width, blockTypes.Air);
def fillBlocks(ix, dx, iy, dy, iz, dz, block, data=None):
    rx = xrange(int(ix), int(ix+dx))
    ry = xrange(int(iy), int(iy+dy))
    rz = xrange(int(iz), int(iz+dz))

    blockList = []
    dataList = []

    [blockList.append((x, y, z, block)) for x,y,z in product(rx, ry, rz)]
    setBlocksAt(blockList)

    if (data != None):
        [dataList.append((x, y, z, data)) for x,y,z in product(rx, ry, rz)]
        setBlocksDataAt(dataList)

# my own setblockat
def setBlockAt(x, y, z, string):
    global arrayBlocks
    arrayKey = '%dx%d' % (x >> chunkWidthPow, z >> chunkWidthPow)
    try:
        myBlocks = arrayBlocks[arrayKey].asarray()
    except KeyError:
        print "got key error with (%d, %d, %d, %s)" % (x, y, z, string)
        myBlocks = arrayBlocks[arrayKey].asarray()
    try:
        materials.materialNamed(string)
    except ValueError:
        print "got value error with (%d, %d, %d, %s)" % (x, y, z, string)
        materials.materialNamed(string)
    myBlocks[x & chunkWidth-1, z & chunkWidth-1, y] = materials.materialNamed(string)

# more aggregates
def setBlocksAt(blocks):
    global arrayBlocks
    for block in blocks:
        (x, y, z, string) = block
        setBlockAt(x, y, z, string)

# my own setblockdataat
def setBlockDataAt(x, y, z, data):
    global arrayData
    arrayKey = '%dx%d' % (x >> chunkWidthPow, z >> chunkWidthPow)
    myData = arrayData[arrayKey].asarray()
    myData[x & chunkWidth-1, z & chunkWidth-1, y] = data

# my own setblocksdataat
def setBlocksDataAt(blocks):
    global arrayData
    for block in blocks:
        (x, y, z, data) = block
        setBlockDataAt(x, y, z, data)

def getBlockAt(x, y, z):
    "Returns the block ID of the block at this point."
    arrayKey = '%dx%d' % (x >> chunkWidthPow, z >> chunkWidthPow)
    myBlocks = arrayBlocks[arrayKey].asarray()
    return materials.names[myBlocks[x & chunkWidth-1, z & chunkWidth-1, y]]
    
def getBlockDataAt(x, y, z):
    "Returns the data value of the block at this point."
    arrayKey = '%dx%d' % (x >> chunkWidthPow, z >> chunkWidthPow)
    myData = arrayData[arrayKey].asarray()
    return myData[x & chunkWidth-1, z & chunkWidth-1, y]

def getBlocksAt(blocks):
    "Returns the block names of the blocks in the list."
    retval = []
    for block in blocks:
        (x, y, z) = block
        arrayKey = '%dx%d' % (x >> chunkWidthPow, z >> chunkWidthPow)
        myBlocks = arrayBlocks[arrayKey].asarray()
        retval.append(materials.names[myBlocks[x & chunkWidth-1, z & chunkWidth-1, y]])
    return retval

# variables
arrayBlocks = {}
arrayData = {}
