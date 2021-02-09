import numpy as np
from structs.numpy import Table
from multical.optimization.parameters import Parameters
from multical import tables


class Static(Parameters):
  def __init__(self, poses):
    self.poses = poses


  def project(self, cameras, camera_poses, world_points):
    return self.reproject(cameras, camera_poses, world_points)


  def reproject(self, cameras, camera_poses, world_points, detected):
    view_table = tables.expand_views(camera_poses, self.poses)
    transformed = tables.transform_points(world_points, view_table)

    image_points = [camera.project(p) for camera, p in 
      zip(self.cameras, transformed.points)]

    return Table.create(points=np.stack(image_points), valid=transformed.valid)

    
  def params(self):
    pass

  def with_params(self, params):
    pass


  def sparsity(self, index_table):
    pass