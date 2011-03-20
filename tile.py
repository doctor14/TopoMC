# tile module
import Image
from time import time
from dataset import *
from coords import *
from invdisttree import *
from bathy import getBathymetry
from crust import getCrust
from dataset import getDatasetDims
from multiprocessing import Pool

def getIDT(ds, offset, size, vScale=1, nodata=None):
    "Convert a portion of a given dataset (identified by corners) to an inverse distance tree."
    # retrieve data from dataset
    Band = ds.GetRasterBand(1)
    Data = Band.ReadAsArray(offset[0], offset[1], size[0], size[1])

    # set nodata if it exists
    if (nodata != None):
        fromnodata = Band.GetNoDataValue()
        Data[Data == fromnodata] = nodata
    Band = None

    # build initial arrays
    LatLong = getLatLongArray(ds, (offset), (size), 1)
    Value = Data.flatten()

    # scale elevation vertically
    Value = Value / vScale

    # build tree
    IDT = Invdisttree(LatLong, Value)

    return IDT

def getOffsetSize(ds, corners, mult=1):
    "Convert corners to offset and size."
    (ul, lr) = corners
    ox, oy = getCoords(ds, ul[0], ul[1])
    offset_x = max(ox, 0)
    offset_y = max(oy, 0)
    fcx, fcy = getCoords(ds, lr[0], lr[1])
    farcorner_x = min(fcx, ds.RasterXSize)
    farcorner_y = min(fcy, ds.RasterYSize)
    offset = (int(offset_x*mult), int(offset_y*mult))
    size = (int(farcorner_x*mult-offset_x*mult), int(farcorner_y*mult-offset_y*mult))
    #print "offset is %d, %d, size is %d, %d" % (offset[0], offset[1], size[0], size[1])
    return offset, size

def getImageArray(ds, idtCorners, baseArray, vScale=1, nodata=None, majority=False):
    "Given the relevant information, builds the image array."
    Offset, Size = getOffsetSize(ds, idtCorners)
    IDT = getIDT(ds, Offset, Size, vScale, nodata)
    ImageArray = IDT(baseArray, nnear=11, eps=0.1, majority=majority)

    return ImageArray

def getTileOffsetSize(rowIndex, colIndex, tileShape, maxRows, maxCols, idtPad=0):
    "run this with idtPad=0 to generate image."
    imageRows = tileShape[0]
    imageCols = tileShape[1]
    imageLeft = max(rowIndex*imageRows-idtPad, 0)
    imageRight = min(imageLeft+imageRows+2*idtPad, maxRows)
    imageUpper = max(colIndex*imageCols-idtPad, 0)
    imageLower = min(imageUpper+imageCols+2*idtPad, maxCols)
    imageOffset = (imageLeft, imageUpper)
    imageSize = (imageRight-imageLeft, imageLower-imageUpper)
    return imageOffset, imageSize

def processTile(args, imagedir, tileRowIndex, tileColIndex):
    "Actually process a tile."
    tileShape = args.tile
    mult = args.mult
    curtime = time()
    (lcds, elevds) = getDataset(args.region)
    (rows, cols) = getDatasetDims(args.region)
    maxRows = int(rows*mult)
    maxCols = int(cols*mult)
    baseOffset, baseSize = getTileOffsetSize(tileRowIndex, tileColIndex, tileShape, maxRows, maxCols)
    idtOffset, idtSize = getTileOffsetSize(tileRowIndex, tileColIndex, tileShape, maxRows, maxCols, idtPad=tileShape[0]+tileShape[1])
    print "Generating tile (%d, %d) with dimensions (%d, %d)..." % (tileRowIndex, tileColIndex, baseSize[0], baseSize[1])

    baseShape = (baseSize[1], baseSize[0])
    baseArray = getLatLongArray(lcds, baseOffset, baseSize, mult)
    #idtShape = (idtSize[1], idtSize[0])
    #idtArray = getLatLongArray(lcds, idtOffset, idtSize, mult)

    # these points are scaled coordinates
    idtUL = getLatLong(lcds, int(idtOffset[0]/mult), int(idtOffset[1]/mult))
    idtLR = getLatLong(lcds, int((idtOffset[0]+idtSize[0])/mult), int((idtOffset[1]+idtSize[1])/mult))

    # nodata for landcover is equal to 11
    lcImageArray = getImageArray(lcds, (idtUL, idtLR), baseArray, nodata=11, majority=True)
    lcImageArray.resize(baseShape)

    elevImageArray = getImageArray(elevds, (idtUL, idtLR), baseArray, args.vscale)
    elevImageArray.resize(baseShape)

    # TODO: go through the arrays for some special transmogrification
    # first idea: bathymetry
    depthOffset, depthSize = getTileOffsetSize(tileRowIndex, tileColIndex, tileShape, maxRows, maxCols, idtPad=args.maxdepth)
    depthShape = (depthSize[1], depthSize[0])
    depthArray = getLatLongArray(lcds, depthOffset, depthSize, mult)
    depthUL = getLatLong(lcds, int(depthOffset[0]/mult), int(depthOffset[1]/mult))
    depthLR = getLatLong(lcds, int((depthOffset[0]+depthSize[0])/mult), int((depthOffset[1]+depthSize[1])/mult))
    bigImageArray = getImageArray(lcds, (depthUL, depthLR), depthArray, majority=True)
    bigImageArray.resize(depthShape)
    bathyImageArray = getBathymetry(args, lcImageArray, bigImageArray, baseOffset, depthOffset)

    # second idea: crust
    crustImageArray = getCrust(bathyImageArray, baseArray)
    crustImageArray.resize(baseShape)
    
    # save images
    lcImage = Image.fromarray(lcImageArray)
    lcImage.save(os.path.join(imagedir, 'lc-%d-%d.gif' % (baseOffset[0], baseOffset[1])))
    lcImage = None
    elevImage = Image.fromarray(elevImageArray)
    elevImage.save(os.path.join(imagedir, 'elev-%d-%d.gif' % (baseOffset[0], baseOffset[1])))
    elevImage = None
    bathyImage = Image.fromarray(bathyImageArray)
    bathyImage.save(os.path.join(imagedir, 'bathy-%d-%d.gif' % (baseOffset[0], baseOffset[1])))
    bathyImage = None
    crustImage = Image.fromarray(crustImageArray)
    crustImage.save(os.path.join(imagedir, 'crust-%d-%d.gif' % (baseOffset[0], baseOffset[1])))
    crustImage = None

    print '... done with (%d, %d) in %f seconds!' % (tileRowIndex, tileColIndex, (time()-curtime))

def processTilestar(args):
    return processTile(*args)

def processTiles(args, imagedir, minTileRows, maxTileRows, minTileCols, maxTileCols):
    "Process tiles."
    if (args.processes == 1):
        [processTile(args, imagedir, tileRowIndex, tileColIndex) for tileRowIndex in xrange(minTileRows, maxTileRows) for tileColIndex in xrange(minTileCols, maxTileCols)]
    else:
        pool = Pool(args.processes)
        tasks = [(args, imagedir, tileRowIndex, tileColIndex) for tileRowIndex in xrange(minTileRows, maxTileRows) for tileColIndex in xrange(minTileCols, maxTileCols)]
        results = pool.imap_unordered(processTilestar, tasks)
        bleah = [x for x in results]
        pool = None

def checkTile(args, mult):
    "Checks to see if a tile dimension is too big for a region."
    oldtilex, oldtiley = args.tile
    rows, cols = getDatasetDims(args.region)
    maxRows = int(rows * mult)
    maxCols = int(cols * mult)
    tilex = min(oldtilex, maxRows)
    tiley = min(oldtiley, maxCols)
    if (tilex != oldtilex or tiley != oldtiley):
        print "Warning: tile size of %d, %d for region %s is too large -- changed to %d, %d" % (oldtilex, oldtiley, args.region, tilex, tiley)
    args.tile = (tilex, tiley)
    return (tilex, tiley)

def checkStartEnd(args, mult, tile):
    "Checks to see if start and end values are valid for a region."
    (rows, cols) = getDatasetDims(args.region)
    (minTileRows, minTileCols) = args.start
    (maxTileRows, maxTileCols) = args.end
    (tileRows, tileCols) = tile

    numRowTiles = int((rows*mult+tileRows-1)/tileRows)
    numColTiles = int((cols*mult+tileCols-1)/tileCols)
    # maxTileRows and maxTileCols default to 0 meaning do everything
    if (maxTileRows == 0 or maxTileRows > numRowTiles):
        if (maxTileRows > numRowTiles):
            print "Warning: maxTileRows greater than numRowTiles, setting to %d" % numRowTiles
        maxTileRows = numRowTiles
    if (minTileRows > maxTileRows):
        print "Warning: minTileRows less than maxTileRows, setting to %d" % maxTileRows
        minTileRows = maxTileRows
    if (maxTileCols == 0 or maxTileCols > numColTiles):
        if (maxTileCols > numColTiles):
            print "Warning: maxTileCols greater than numColTiles, setting to %d" % numColTiles
        maxTileCols = numColTiles
    if (minTileCols > maxTileCols):
        print "Warning: minTileCols less than maxTileCols, setting to %d" % maxTileCols
        minTileCols = maxTileCols
    return (minTileRows, minTileCols, maxTileRows, maxTileCols)

