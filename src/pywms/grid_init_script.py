'''
Created on Sep 6, 2011

@author: ACrosby
'''
from netCDF4 import Dataset as ncDataset
from netCDF4 import num2date
import sys, os, numpy, logging, traceback
from datetime import datetime
import numpy as np
from pywms.wms.models import Dataset
import server_local_config
import multiprocessing
from collections import deque
try:
    import cPickle as pickle
except: 
    import Pickle as pickle
    
s = multiprocessing.Semaphore(2)

output_path = 'sciwms_wms'
# Set up Logger
logger = multiprocessing.get_logger()
logger.setLevel(logging.INFO)
handler = logging.FileHandler('%s.log' % output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)

def create_topology(datasetname, url):
    import server_local_config as config
    nc = ncDataset(url)
    nclocalpath = os.path.join(config.topologypath, datasetname+".nc")
    nclocal = ncDataset(nclocalpath, mode="w", clobber=True)
    if nc.variables.has_key("nv"):
        nclocal.createDimension('cell', nc.variables['latc'].shape[0])#90415)
        nclocal.createDimension('node', nc.variables['lat'].shape[0])
        nclocal.createDimension('time', nc.variables['time'].shape[0])
        nclocal.createDimension('corners', nc.variables['nv'].shape[0])
 
        lat = nclocal.createVariable('lat', 'f', ('node',), chunksizes=nc.variables['lat'].shape, zlib=False, complevel=0)
        lon = nclocal.createVariable('lon', 'f', ('node',), chunksizes=nc.variables['lat'].shape, zlib=False, complevel=0)
        latc = nclocal.createVariable('latc', 'f', ('cell',), chunksizes=nc.variables['latc'].shape, zlib=False, complevel=0)
        lonc = nclocal.createVariable('lonc', 'f', ('cell',), chunksizes=nc.variables['latc'].shape, zlib=False, complevel=0)
        nv = nclocal.createVariable('nv', 'u8', ('corners', 'cell',), chunksizes=nc.variables['nv'].shape, zlib=False, complevel=0)

        time = nclocal.createVariable('time', 'f8', ('time',), chunksizes=nc.variables['time'].shape, zlib=False, complevel=0) #d 
        
        lontemp = nc.variables['lon'][:]
        if np.max(lontemp) > 180:
            #print "greaterthan"
            lonctemp = nc.variables['lonc'][:]
            lontemp[lontemp > 180] = lontemp[lontemp > 180] - 360
            lonctemp[lonctemp > 180] = lonctemp[lonctemp > 180] -360
            lon[:] = np.asarray(lontemp)
            lonc[:] = np.asarray(lonctemp)
        #elif np.min(lontemp) < -180:
        #    print "lessthan"
        #    lon[:] = np.asarray(lontemp) + 360
        #    lonc[:] = np.asarray(nc.variables['lonc'][:] + 360)
        else:
        #    print "nochange"
            lon[:] = lontemp
            lonc[:] = nc.variables['lonc'][:]
                
        lat[:] = nc.variables['lat'][:]
        latc[:] = nc.variables['latc'][:]
        
        nv[:,:] = nc.variables['nv'][:,:]
        time[:] = nc.variables['time'][:]
        time.units = nc.variables['time'].units
    
    elif nc.variables.has_key("element"):
        nclocal.createDimension('node', nc.variables['x'].shape[0])
        nclocal.createDimension('cell', nc.variables['element'].shape[0])
        nclocal.createDimension('time', nc.variables['time'].shape[0])
        nclocal.createDimension('corners', nc.variables['element'].shape[1])

        lat = nclocal.createVariable('lat', 'f', ('node',), chunksizes=(nc.variables['x'].shape[0],), zlib=False, complevel=0)
        lon = nclocal.createVariable('lon', 'f', ('node',), chunksizes=(nc.variables['x'].shape[0],), zlib=False, complevel=0)
        latc = nclocal.createVariable('latc', 'f', ('cell',), chunksizes=(nc.variables['element'].shape[0],), zlib=False, complevel=0)
        lonc = nclocal.createVariable('lonc', 'f', ('cell',), chunksizes=(nc.variables['element'].shape[0],), zlib=False, complevel=0)
        nv = nclocal.createVariable('nv', 'u8', ('corners', 'cell',), chunksizes=nc.variables['element'].shape[::-1], zlib=False, complevel=0)

        time = nclocal.createVariable('time', 'f8', ('time',), chunksizes=nc.variables['time'].shape, zlib=False, complevel=0) 
        
        lattemp = nc.variables['y'][:]
        lontemp = nc.variables['x'][:]
        lat[:] = lattemp
        lontemp[lontemp > 180] = lontemp[lontemp > 180] - 360
        
        lon[:] = lontemp
        import matplotlib.tri as Tri
        tri = Tri.Triangulation(lontemp, 
                                lattemp,
                                nc.variables['element'][:,:]-1
                                )
        
        lonc[:] = lontemp[tri.triangles].mean(axis=1)
        latc[:] = lattemp[tri.triangles].mean(axis=1)
        nv[:,:] = nc.variables['element'][:,:].T
        time[:] = nc.variables['time'][:]
        time.units = nc.variables['time'].units
    
    
    
    nclocal.sync()
    nclocal.close()
    nc.close()
    create_domain_polygon(nclocalpath)
    
def create_topology_from_config():
    """
    Initialize topology upon server start up for each of the datasets listed in server_local_config.datasetpath dictionary
    """    
    datasets = Dataset.objects.values()
    for dataset in datasets:
        print "Adding: " + dataset["name"]
        create_topology(dataset["name"], dataset["uri"])


def check_topology_age():
    try:
        from datetime import datetime
        if True:
            datasets = Dataset.objects.values()
            jobs = []
            for dataset in datasets:
                #print dataset
                name = dataset["name"]
                p = multiprocessing.Process(target=do, args=(name,dataset,s))
                p.daemon = True
                p.start()
                jobs.append(p)
                #do(name, dataset)
    except Exception as detail:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " +\
                                 repr(traceback.format_exception(exc_type, exc_value,
                                              exc_traceback)))
def do(name, dataset, s):
    with s:
        try:
            try:
                #get_lock()
                filemtime = datetime.fromtimestamp(
                    os.path.getmtime(
                    os.path.join(
                    server_local_config.topologypath, name + ".nc"
                    )))
                #print filemtime
                difference = datetime.now() - filemtime
                if dataset["keep_up_to_date"]:
                    if difference.seconds > .5*3600 or difference.days > 0:
                        
                        nc = ncDataset(dataset["uri"])
                        topo = ncDataset(os.path.join(
                            server_local_config.topologypath, name + ".nc"))
                            
                        time1 = nc.variables['time'][-1]
                        time2 = topo.variables['time'][-1]
                        
                        nc.close()
                        topo.close()
                        if time1 != time2:    
                            print "Updating: " + dataset["uri"]
                            create_topology(name, dataset["uri"])

            except:
                print "Initializing: " + dataset["uri"]
                create_topology(name, dataset["uri"])
            try:
                nc.close()
                topo.close()
            except:
                pass
        except Exception as detail:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error("Disabling Error: " +\
                                 repr(traceback.format_exception(exc_type, exc_value,
                                              exc_traceback)))
    
def create_domain_polygon(filename):
    from shapely.geometry import Polygon
    from shapely.ops import cascaded_union
    nc = ncDataset(filename)
    nv = nc.variables['nv'][:, :].T-1
    latn = nc.variables['lat'][:]
    lonn = nc.variables['lon'][:]
    lon = nc.variables['lonc'][:]
    lat = nc.variables['latc'][:]
    index_pos = numpy.asarray(numpy.where(
            (lat <= 90) & (lat >= -90) &
            (lon <= 180) & (lon > 0),)).squeeze()
    index_neg = numpy.asarray(numpy.where(
            (lat <= 90) & (lat >= -90) &
            (lon < 0) & (lon >= -180),)).squeeze()
    if len(index_pos) > 0:       
        p = deque()
        p_add = p.append
        for i in index_pos:
            flon, flat = lonn[nv[i,0]], latn[nv[i,0]]
            lon1, lat1 = lonn[nv[i,1]], latn[nv[i,1]]
            lon2, lat2 = lonn[nv[i,2]], latn[nv[i,2]] 
            if flon < -90:
                flon = flon + 360
            if lon1 < -90:
                lon1 = lon1 + 360
            if lon2 < -90:
                lon2 = lon2 + 360
            p_add(Polygon(((flon, flat),
                           (lon1, lat1),
                           (lon2, lat2),
                           (flon, flat),)))
        domain_pos = cascaded_union(p)  
    if len(index_neg) > 0: 
        p = deque()
        p_add = p.append
        for i in index_neg:
            flon, flat = lonn[nv[i,0]], latn[nv[i,0]]
            lon1, lat1 = lonn[nv[i,1]], latn[nv[i,1]]
            lon2, lat2 = lonn[nv[i,2]], latn[nv[i,2]]
            if flon > 90:
                flon = flon - 360
            if lon1 > 90:
                lon1 = lon1 - 360
            if lon2 > 90:
                lon2 = lon2 - 360
            p_add(Polygon(((flon, flat),
                           (lon1, lat1),
                           (lon2, lat2),
                           (flon, flat),)))
        domain_neg = cascaded_union(p)
    if len(index_neg) > 0 and len(index_pos) > 0:
        domain = cascaded_union((domain_neg, domain_pos,))
    elif len(index_neg) > 0:
        domain = domain_neg
    elif len(index_pos) > 0:
        domain = domain_pos
    else:
        raise ValueError("No data in file")

    f = open(filename[:-3] + '.domain', 'w')
    pickle.dump(domain, f)
    f.close()

    nc.close()

## Cannot be called as a script any more because of the 
## dependence on the django framework/database stuff
'''    
if __name__ == '__main__':
    """
    Initialize topology upon server start up for each of the datasets listed in server_local_config.datasetpath dictionary
       
    import server_local_config

    paths = server_local_config.datasetpath #dict
    for dataset in paths.viewkeys():
        print "Adding: " + paths[dataset]
        create_topology(dataset, paths[dataset])
    """
    create_topology_from_config()
''' 






