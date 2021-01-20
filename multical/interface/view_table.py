import math
from os import path

from PyQt5.QtGui import QBrush, QColor
from multical import tables

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QAbstractTableModel
import numpy as np

from structs.struct import struct
from structs.numpy import shape, Table

from colour import Color


def masked_quantile(error, mask, quantiles, axis=None):
  error = error.copy()
  error[~mask] = math.nan

  return np.nanquantile(error, quantiles, axis=axis)


def reprojection_statistics(error, valid, inlier, axis=None):
  n = valid.sum(axis=axis)
  mse = np.square(error).sum(axis=axis) / np.maximum(n, 1)

  outliers = (valid & ~inlier).sum(axis=axis)
  quantiles = masked_quantile(
      error, valid, [0, 0.25, 0.5, 0.75, 1.0], axis=axis)
  min, lq, median, uq, max = quantiles

  return Table.create(detected=n, outliers=outliers, mse=mse, rms=np.sqrt(mse),
                      min=min, lower_q=lq, median=median, upper_q=uq, max=max)


def reprojection_tables(calib, inlier_only=False):
  point_table = calib.point_table
  if inlier_only:
    point_table = point_table._extend(valid_points=calib.inliers)

  error, valid = tables.reprojection_error(calib.projected, point_table)

  def f(axis): return reprojection_statistics(
      error, valid, calib.inliers, axis=axis)
  axes = struct(overall=None, views=2, cameras=(1, 2), frames=(0, 2))
  return axes._map(f)


def detection_tables(point_table):
  valid = point_table.valid_points
  def f(axis): return np.sum(valid, axis=axis)

  axes = struct(overall=None, views=(2, 3), cameras=(
      1, 2, 3), frames=(0, 2, 3), boards=(0, 1, 3))
  return axes._map(f)


def interpolate_hsl(t, color1, color2):
  hsl1 = np.array(color1.get_hsl())
  hsl2 = np.array(color2.get_hsl())
  return Color(hsl=hsl2 * t + hsl1 * (1 - t))


class ViewModelCalibrated(QAbstractTableModel):
  def __init__(self, calib, camera_names, image_names):
    super(ViewModelCalibrated, self).__init__()

    self.calib = calib
    self.reprojection_table = reprojection_tables(calib)
    self.inlier_table = reprojection_tables(calib, inlier_only=True)

    self.camera_names = camera_names
    self.image_names = image_names

    self.metrics = dict(
        detected='Detected (Outliers)',
        median='Median',
        upper_q='Upper quartile',
        max='Maximum',
        rms='Root Mean Square',
        mse='Mean Square Error'
    )

    self.colors = struct(
        inliers=Color(rgb=(0, 1, 0)),
        outliers=Color(rgb=(1, 0, 0))
    )

    self.metric = 'detected'
    self.inlier_only = False

  @property
  def metric_labels(self):
    return list(self.metrics.values())

  @property
  def view_table(self):
    return self.reprojection_table.views\
        if not self.inlier_only else self.inlier_table.views

  def cell_color(self, view_stats):
    detection_rate = min(view_stats.detected / self.calib.board.num_points, 1)
    outlier_rate = view_stats.outliers / max(view_stats.detected, 1)

    outlier_t = min(outlier_rate * 5, 1.0)
    color = interpolate_hsl(
        outlier_t, self.colors.inliers, self.colors.outliers)

    color.set_luminance(max(1 - detection_rate, 0.7))
    return color

  def set_metric(self, metric, inlier_only=False):

    if isinstance(metric, str):
      assert metric in self.metrics
      self.metric = metric
    else:
      assert isinstance(metric, int)
      metric_list = list(self.metrics.keys())
      self.metric = metric_list[metric]

    self.inlier_only = inlier_only
    self.modelReset.emit()

  def data(self, index, role):

    if role == Qt.DisplayRole:
      view_stats = self.view_table._index[index.column(), index.row()]

      if self.metric == "detected":
        return f"{view_stats.detected} ({view_stats.outliers})"
      else:
        return f"{view_stats[self.metric]:.2f}"

    if role == Qt.BackgroundRole:
      view_table = self.reprojection_table.views
      view_stats = view_table._index[index.column(), index.row()]

      rgb = np.array(self.cell_color(view_stats).get_rgb()) * 255

      return QBrush(QColor(*rgb))

  def headerData(self, index, orientation, role):
    if role == Qt.DisplayRole:
      if orientation == Qt.Horizontal:
        return self.camera_names[index]
      else:
        return path.splitext(self.image_names[index])[0]

  def rowCount(self, index):
    return self.view_table._shape[1]

  def columnCount(self, index):
    return self.view_table._shape[0]


class ViewModelDetections(QAbstractTableModel):
  def __init__(self, point_table, camera_names, image_names):
    super(ViewModelDetections, self).__init__()

    self.point_table = point_table
    self.camera_names = camera_names
    self.image_names = image_names

    self.detection_table = detection_tables(point_table)
    self.quantiles = np.quantile(self.detection_table.views.flatten(), [0, 0.25, 0.5, 0.75, 1.0]) 

    self.metrics = dict(
        total='Total'
    )

    self.colors = struct(
        detected=Color(rgb=(0, 1, 0))
    )

    self.metric = 'total'

  @property
  def metric_labels(self):
    return list(self.metrics.values())

  @property
  def view_table(self):
    return self.detection_table.views

  def cell_color(self, detection_count):
    color = self.colors.detected
    detection_rate = min(detection_count / self.quantiles[3], 1)

    color.set_luminance(max(1 - detection_rate, 0.7))
    return color

  def set_metric(self, metric, inlier_only=False):

    if isinstance(metric, str):
      assert metric in self.metrics
      self.metric = metric
    else:
      assert isinstance(metric, int)
      metric_list = list(self.metrics.keys())
      self.metric = metric_list[metric]

    self.inlier_only = inlier_only
    self.modelReset.emit()

  def data(self, index, role):

    if role == Qt.DisplayRole:
      view_stats = self.view_table._index[index.column(), index.row()]

      if self.metric == "detected":
        return f"{view_stats.detected} ({view_stats.outliers})"
      else:
        return f"{view_stats[self.metric]:.2f}"

    if role == Qt.BackgroundRole:
      view_table = self.reprojection_table.views
      view_stats = view_table._index[index.column(), index.row()]

      rgb = np.array(self.cell_color(view_stats).get_rgb()) * 255

      return QBrush(QColor(*rgb))

  def headerData(self, index, orientation, role):
    if role == Qt.DisplayRole:
      if orientation == Qt.Horizontal:
        return self.camera_names[index]
      else:
        return path.splitext(self.image_names[index])[0]

  def rowCount(self, index):
    return self.view_table._shape[1]

  def columnCount(self, index):
    return self.view_table._shape[0]
