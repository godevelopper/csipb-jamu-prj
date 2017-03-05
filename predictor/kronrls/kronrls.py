# kronrls.py
import numpy as np
import sys

sys.path.append('../../config')
from predictor_config import kronRLSConfig
from predictor_config import predictorConfig as pcfg
from database_config import databaseConfig as dcfg

sys.path.append('../../utility')
import postgresql_util as pgUtil

from numpy import linalg as LA
from scipy import sparse
from collections import defaultdict

class KronRLS:
    def __init__(self,iparam,
                 iTrConnMat=None,iTrComList=None,iTrProList=None,iKernelDict=None):
        self._param = iparam

        self._trConnMat = None
        self._trComList = None
        self._trProList = None
        self._kernelDict = None

        if iTrConnMat!=None:
            self._trConnMat = iTrConnMat
            self._trComList = iTrComList
            self._trProList = iTrProList
            self._kernelDict = iKernelDict

    def predict(self,xTest):
        ## train, local training: one for every predict()
        model = self._train(xTest)
        connMat,comKernelMat,proKernelMat,xIdxTest = model

        ## make prediction
        gamma = self._param['gamma']
        connMatPred = self._predict(comKernelMat,proKernelMat,connMat,gamma)

        ##
        yPred = []
        for cIdx,pIdx in xIdxTest:
            y = connMatPred[cIdx][pIdx]
            y = int(y>=self._param['threshold'])
            yPred.append(y)

        return yPred

    def close(self):
        self.dbConn.close()

    def _train(self,xTest):
        '''
        in kronRLS, the (learned) model refers to the connMat and  the kernel
        '''
        ## make connMat
        comList = None
        proList = None
        connMat = None
        if self._trConnMat!=None:
            comList = self._trComList
            proList = self._trProList
            connMat = self._trConnMat
        else:# draw connMat from DB
            nMax = self._param['maxTrainingDataSize']
            sources = pcfg['trainingDataSources']
            connMat,comList,proList = pgUtil.drawConnMat(nMax,sources)

        ## clear any element of connMat that is in testing set
        xIdxTest = []
        for c,p in xTest:
            cIdx = -1
            if c in comList:
                cIdx = comList.index(c)
            else:
                nCol = connMat.shape[1]
                newConn = np.zeros( (1,nCol) )
                connMat = np.vstack( (connMat,newConn) )
                comList.append(c)
                cIdx = len(comList)-1

            pIdx = -1
            if p in proList:
                pIdx = proList.index(p)
            else:
                nRow = connMat.shape[0]
                newConn  = np.zeros( (nRow,1) )
                connMat = np.hstack( (connMat,newConn) )
                proList.append(p)
                pIdx = len(proList)-1

            if cIdx!=-1 and pIdx!=-1:
                connMat[cIdx][pIdx] = 0 # yes, setting to zero for test samples

            xIdxTest.append( (cIdx,pIdx) )

        ##
        comKernelMat = self._makeKernelMat(comList,comList)
        proKernelMat = self._makeKernelMat(proList,proList)

        ##
        model = (connMat,comKernelMat,proKernelMat,xIdxTest)

        return model

    def _predict(self,k1,k2,y,gamma):
        la,Qa = LA.eig(k1)
        lb,Qb = LA.eig(k2)

        la = la.flatten()
        lb = lb.flatten()
        la = np.diag(la)
        lb = np.diag(lb)

        # http://stackoverflow.com/questions/17035767/kronecker-product-in-python-and-matlab
        diagLa = np.diag(la)
        diagLa = diagLa.reshape((len(diagLa),1))
        diagLbTrans = np.diag(lb).transpose()
        diagLbTrans = diagLbTrans.reshape((1,len(diagLbTrans)))

        l = sparse.kron( diagLbTrans,diagLa ).toarray()
        inverse = l / (l+gamma)

        m1 = Qa.transpose().dot(y).dot(Qb)
        m2 = m1 * inverse

        ypred = Qa.dot(m2).dot( Qb.transpose() )
        ypred = ypred.real

        return ypred

    def _makeKernelMat(self,list1,list2):
        kernelDict = None
        if self._kernelDict!=None:
            kernelDict = self._kernelDict
        else:
            kernelDict = pgUtil.drawKernel( list(set(list1+list2)) )

        m = len(list1); n = len(list2)
        kernel = np.zeros((m,n))
        for i,ii in enumerate(list1):
            for j,jj in enumerate(list2):
                key = (ii,jj)
                sim = 0.0
                if key in kernelDict:
                    sim = kernelDict[key]
                kernel[i][j] = sim

        return kernel

def test():
    predictor = KronRLS(kronRLSConfig)

    xTest = [('COM00014256','PRO00001554')]
    yPreds = predictor.predict(xTest)

if __name__ == '__main__':
    test()
