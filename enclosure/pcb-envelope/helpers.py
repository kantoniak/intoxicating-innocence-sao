from enum import Enum
from itertools import pairwise
from typing import Iterable
import FreeCAD as App
import Part
import Sketcher


class AxisId(int, Enum):
  X = -1 # Horizontal
  Y = -2 # Vertical


class ConstraintAttachment(int, Enum):
  EDGE = 0
  START_POINT = 1
  END_POINT = 2
  CENTER = 3 # For ellipses and arcs only


ORIGIN = (AxisId.X, ConstraintAttachment.START_POINT)


def initParams(doc, params: dict):
  sheet_label = "Params"
  ss = doc.addObject("Spreadsheet::Sheet", sheet_label)

  row = 1
  for name, value in params.items():
    if isinstance(value, str):
        val_str = value
    else:
        val_str = str(value)

    ss.set(f"A{row}", name)
    ss.set(f"B{row}", val_str)
    ss.setAlias(f"B{row}", name)

    row += 1

  doc.recompute()
  enum_members = {k: f"{sheet_label}.{k}" for k in params.keys()}

  class StrEnum(str, Enum):
    pass

  return StrEnum(sheet_label, enum_members)


def addExternalGeomIndexed(sketch, obj, subName: str) -> int:
  index = int(-3 - len(sketch.ExternalGeometry))
  sketch.addExternal(obj.Name, subName)
  return index


def addExpressionConstraint(sketch, name: str, expr: str, *constraint_args) -> int:
  args = (name,) + tuple(constraint_args) + (1,)
  constraint_id = sketch.addConstraint(Sketcher.Constraint(*args))
  print(f'{sketch.Label}.Constraints[{constraint_id}]: {expr}')
  sketch.setExpression(f'Constraints[{constraint_id}]', expr)
  return int(constraint_id)


def constrainCoincidentPath(geometry: Iterable[int], loop: bool = False):
  if loop:
    geometry.append(geometry[0])
  objects = pairwise(geometry)
  return [Sketcher.Constraint('Coincident', a, ConstraintAttachment.END_POINT, b, ConstraintAttachment.START_POINT)
      for a, b in objects]


def addRectangle(sketch, x1: float, y1: float, x2: float, y2: float):
  # Corner points
  p_tl = App.Vector(x1, y1, 0)
  p_tr = App.Vector(x2, y1, 0)
  p_br = App.Vector(x2, y2, 0)
  p_bl = App.Vector(x1, y2, 0)

  # Edges
  i1 = sketch.addGeometry(Part.LineSegment(p_tl, p_tr), False)  # top edge
  i2 = sketch.addGeometry(Part.LineSegment(p_tr, p_br), False)  # right edge
  i3 = sketch.addGeometry(Part.LineSegment(p_br, p_bl), False)  # bottom edge
  i4 = sketch.addGeometry(Part.LineSegment(p_bl, p_tl), False)  # left edge

  # Close rectangle: make endpoints coincident
  # Line segment point indices: 1 = start point, 2 = end point
  sketch.addConstraint(Sketcher.Constraint('Coincident', i1, 2, i2, 1))
  sketch.addConstraint(Sketcher.Constraint('Coincident', i2, 2, i3, 1))
  sketch.addConstraint(Sketcher.Constraint('Coincident', i3, 2, i4, 1))
  sketch.addConstraint(Sketcher.Constraint('Coincident', i4, 2, i1, 1))

  # Constrain vertical/horizontal edges
  sketch.addConstraint(Sketcher.Constraint('Horizontal', i1))  # top edge
  sketch.addConstraint(Sketcher.Constraint('Vertical', i2))    # right edge
  sketch.addConstraint(Sketcher.Constraint('Horizontal', i3))  # bottom edge
  sketch.addConstraint(Sketcher.Constraint('Vertical', i4))    # left edge

  return (i1, i2, i3, i4)


def addCenteredRectangle(sketch, width_expr, height_expr, around_obj, around_attachment):
  (top, right, bottom, left) = addRectangle(sketch, -1, 1, 1, -1)
  sketch.addConstraint(Sketcher.Constraint('Symmetric', right, ConstraintAttachment.END_POINT, left, ConstraintAttachment.END_POINT, around_obj, around_attachment))
  addExpressionConstraint(sketch, 'DistanceX', width_expr, left, ConstraintAttachment.START_POINT, right, ConstraintAttachment.END_POINT)
  addExpressionConstraint(sketch, 'DistanceY', height_expr, bottom, ConstraintAttachment.START_POINT, top, ConstraintAttachment.END_POINT)
  return (top, right, bottom, left)


def addOctagon(sketch):
  circle = sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1.000000), 1))
  sketch.toggleConstruction(circle)

  points = [
    App.Vector(-2, 1),
    App.Vector(-2, -1),
    App.Vector(-1, -2),
    App.Vector(1, -2),
    App.Vector(2, -1),
    App.Vector(2, 1),
    App.Vector(1, 2),
    App.Vector(-1, 2),
  ]

  lines = sketch.addGeometry(
    [Part.LineSegment(a, b) for a, b in pairwise(points)] + [Part.LineSegment(points[-1], points[0])],
    False)

  sketch.addConstraint(
    [Sketcher.Constraint('Coincident', a, ConstraintAttachment.END_POINT, b, ConstraintAttachment.START_POINT) for a, b in pairwise(lines)] +
    [Sketcher.Constraint('Coincident', lines[-1], ConstraintAttachment.END_POINT, lines[0], ConstraintAttachment.START_POINT)] +
    [Sketcher.Constraint('PointOnObject', l, ConstraintAttachment.START_POINT, circle) for l in lines] +
    [Sketcher.Constraint('Equal', lines[0], l) for l in lines[1:]])

  return circle, lines

def toSurfaceFromSketchEdges(parent, sketch):
  sketch.recompute()
  edge_count = len(sketch.Shape.Edges)
  surface = parent.newObject("Surface::Filling", f"Surface_{sketch.Label}")
  surface.BoundaryEdges = [(sketch, f"Edge{i}") for i in range(1, edge_count+1)]
  return surface
