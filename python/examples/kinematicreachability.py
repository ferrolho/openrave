#!/usr/bin/env python
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import with_statement # for python 2.5
__author__ = 'Rosen Diankov'
__copyright__ = 'Copyright (C) 2009-2010 Rosen Diankov (rosen.diankov@gmail.com)'
__license__ = 'Apache License, Version 2.0'

import openravepy
from openravepy import *
from openravepy.examples import inversekinematics
from numpy import *
import time
import heapq # for nth smallest element
from optparse import OptionParser

class ReachabilityModel(OpenRAVEModel):
    """Computes the robot manipulator's reachability space (stores it in 6D) and
    offers several functions to use it effectively in planning."""
    def __init__(self,robot):
        OpenRAVEModel.__init__(self,robot=robot)
        self.ikmodel = inversekinematics.InverseKinematicsModel(robot=robot)
        if not self.ikmodel.load():
            self.ikmodel.autogenerate()
        self.reachabilitystats = None
        self.reachabilitydensity3d = None
        self.pointscale = None
        self.xyzdelta = None
        self.quatdelta = None

    def has(self):
        return len(self.reachabilitydensity3d) > 0

    def load(self):
        try:
            params = OpenRAVEModel.load(self)
            if params is None:
                return False
            self.reachabilitystats,self.reachabilitydensity3d,self.pointscale,self.xyzdelta,self.quatdelta = params
            return self.has()
        except e:
            return False
    def save(self):
        OpenRAVEModel.save(self,(self.reachabilitystats,self.reachabilitydensity3d,self.pointscale,self.xyzdelta,self.quatdelta))

    def getfilename(self):
        return os.path.join(OpenRAVEModel.getfilename(self),'reachability.' + self.manip.GetName() + '.pp')

    def generateFromOptions(self,options):
        self.generate(maxradius=options.maxradius,xyzdelta=options.xyzdelta,quatdelta=options.quatdelta)

    def generate(self,maxradius=None,translationonly=False,xyzdelta=0.04,quatdelta=0.5):
        starttime = time.time()
        with self.robot:
            self.robot.SetTransform(eye(4))
            
            # the axes' anchors are the best way to find th emax radius
            eeanchor = self.robot.GetJoints()[self.manip.GetArmJoints()[-1]].GetAnchor()
            eetrans = self.manip.GetEndEffectorTransform()[0:3,3]
            baseanchor = self.robot.GetJoints()[self.manip.GetArmJoints()[0]].GetAnchor()
            armlength = sqrt(sum((eetrans-baseanchor)**2))
            if maxradius is None:
                maxradius = armlength+0.05

            allpoints,insideinds,shape,self.pointscale = self.UniformlySampleSpace(maxradius,delta=xyzdelta)
            # select the best sphere level matching quatdelta;
            # level=0, quatdist = 0.5160220
            # level=1: quatdist = 0.2523583
            # level=2: quatdist = 0.120735
            qarray = SpaceSampler().sampleSO3(level=max(0,int(-0.5-log2(quatdelta))))
            rotations = [eye(3)] if translationonly else rotationMatrixFromQArray(qarray)
            self.xyzdelta = xyzdelta
            self.quatdelta = 0
            if not translationonly:
                # for rotations, get the average distance to the nearest rotation
                neighdists = []
                for q in qarray:
                    neighdists.append(heapq.nsmallest(2,quatArrayTDist(q,qarray))[1])
                self.quatdelta = mean(neighdists)

            print 'radius: %f, xyzsamples: %d, quatdelta: %f, rot samples: %d'%(maxradius,len(insideinds),self.quatdelta,len(rotations))
            T = eye(4)
            reachabilitydensity3d = zeros(prod(shape))
            self.reachabilitystats = []
            with self.env:
                for i,ind in enumerate(insideinds):
                    numvalid = 0
                    T[0:3,3] = allpoints[ind]+baseanchor
                    for rotation in rotations:
                        T[0:3,0:3] = rotation
                        solutions = self.manip.FindIKSolutions(T,False) # do not want to include the environment
                        if solutions is not None:
                            self.reachabilitystats.append(r_[poseFromMatrix(T),len(solutions)])
                            numvalid += len(solutions)
                    if mod(i,1000)==0:
                        print '%d/%d'%(i,len(insideinds))
                    reachabilitydensity3d[ind] = numvalid/float(len(rotations))
            self.reachabilitydensity3d = reshape(reachabilitydensity3d/50.0,shape)
            self.reachabilitystats = array(self.reachabilitystats)
            print 'reachability finished in %fs'%(time.time()-starttime)

    def show(self,showrobot=True,contours=[0.01,0.1,0.5,0.9,0.99],opacity=None,figureid=1, xrange=None,options=None):
        mlab.figure(figureid,fgcolor=(0,0,0), bgcolor=(1,1,1),size=(1024,768))
        mlab.clf()

#         minpoint = numpy.min(self.reachabilitystats[:,4:7],0)
#         maxpoint = numpy.max(self.reachabilitystats[:,4:7],0)
#         N = ceil(maxpoint-minpoint)/self.xyzdelta
#         X,Y,Z = mgrid[minpoint[0]:maxpoint[0]:self.xyzdelta,minpoint[1]:maxpoint[1]:self.xyzdelta,minpoint[2]:maxpoint[2]:self.xyzdelta]
#         kdtree = pyANN.KDTree(self.reachabilitystats[:,4:7])
#         neighs,dists,kball = kdtree.kFRSearchArray(c_[X.flat,Y.flat,Z.flat],1.5*self.xyzdelta**2,0,self.xyzdelta*0.01)
#         reachabilitydensity3d = reshape(array(kball,'float'),X.shape)*0.01

        if options is not None:
            reachabilitydensity3d = minimum(self.reachabilitydensity3d*options.showscale,1.0)
        else:
            reachabilitydensity3d = minimum(self.reachabilitydensity3d,1.0)
        reachabilitydensity3d[0,0,0] = 1 # have at least one point be at the maximum
        if xrange is None:
            offset = array((0,0,0))
            src = mlab.pipeline.scalar_field(reachabilitydensity3d)
        else:
            offset = array((xrange[0]-1,0,0))
            src = mlab.pipeline.scalar_field(r_[zeros((1,)+reachabilitydensity3d.shape[1:]),reachabilitydensity3d[xrange,:,:],zeros((1,)+reachabilitydensity3d.shape[1:])])
            
        for i,c in enumerate(contours):
            mlab.pipeline.iso_surface(src,contours=[c],opacity=min(1,0.7*c if opacity is None else opacity[i]))
        #mlab.pipeline.volume(mlab.pipeline.scalar_field(reachabilitydensity3d*100))
        if showrobot:
            baseanchor = self.robot.GetJoints()[self.manip.GetArmJoints()[0]].GetAnchor()
            with self.robot:
                self.robot.SetTransform(eye(4))
                trimesh = self.env.Triangulate(self.robot)
            v = self.pointscale[0]*(trimesh.vertices-tile(baseanchor,(len(trimesh.vertices),1)))+self.pointscale[1]
            mlab.triangular_mesh(v[:,0]-offset[0],v[:,1]-offset[1],v[:,2]-offset[2],trimesh.indices,color=(0.5,0.5,0.5))
        mlab.show()

    def autogenerate(self,forcegenerate=True):
        # disable every body but the target and robot
        bodies = [b for b in self.env.GetBodies() if b.GetNetworkId() != self.robot.GetNetworkId()]
        for b in bodies:
            b.Enable(False)
        try:
            if self.robot.GetRobotStructureHash() == '409764e862c254605cafb9de013eb531' and self.manip.GetName() == 'arm':
                self.generate(maxradius=1.1)
            else:
                if not forcegenerate:
                    raise ValueError('failed to find auto-generation parameters')
                self.generate()
            self.save()
        finally:
            for b in bodies:
                b.Enable(True)

    def UniformlySampleSpace(self,maxradius,delta):
        nsteps = floor(maxradius/delta)
        X,Y,Z = mgrid[-nsteps:nsteps,-nsteps:nsteps,-nsteps:nsteps]
        allpoints = c_[X.flat,Y.flat,Z.flat]*delta
        insideinds = flatnonzero(sum(allpoints**2,1)<maxradius**2)
        return allpoints,insideinds,X.shape,array((1.0/delta,nsteps))

    @staticmethod
    def CreateOptionParser():
        parser = OpenRAVEModel.CreateOptionParser()
        parser.description='Computes the reachability region of a robot manipulator and python pickles it into a file.'
        parser.add_option('--maxradius',action='store',type='float',dest='maxradius',default=None,
                          help='The max radius of the arm to perform the computation')
        parser.add_option('--xyzdelta',action='store',type='float',dest='xyzdelta',default=0.04,
                          help='The max radius of the arm to perform the computation (default=%default)')
        parser.add_option('--quatdelta',action='store',type='float',dest='quatdelta',default=0.5,
                          help='The max radius of the arm to perform the computation (default=%default)')
        parser.add_option('--showscale',action='store',type='float',dest='showscale',default=1.0,
                          help='Scales the reachability by this much in order to show colors better (default=%default)')
        return parser
    @staticmethod
    def RunFromParser(Model=None,parser=None):
        if parser is None:
            parser = ReachabilityModel.CreateOptionParser()
        (options, args) = parser.parse_args()
        env = Environment()
        try:
            if Model is None:
                Model = lambda robot: ReachabilityModel(robot=robot)
            OpenRAVEModel.RunFromParser(env=env,Model=Model,parser=parser)
        finally:
            env.Destroy()

if __name__=='__main__':
    try:
        from enthought.mayavi import mlab
    except ImportError:
        pass
    ReachabilityModel.RunFromParser()
