from helpers import *
from helpers import ConstraintAttachment as CA
import importDXF
import math
import Draft
import FreeCAD as App
import MeshPart, Mesh

IMPORT_STEP = True
EXPORT_DXF = False
EXPORT_STL = False

doc = App.newDocument("Enclosure")
Params = initParams(doc, {
  'PCB_THICKNESS': '1.6 mm',
  'PCB_OUTLINE_TOLERANCE': '0.2 mm', # Regular
  'PCB_RADIUS': '18 mm',
  'PCB_BOTTOM_HALF_HEIGHT': '14 mm',
  'PLA_EXPANSION': '0.2 mm',
  'HEAT_INSERT_HOLE_DIAM': '3.2 mm',
  'HEAT_INSERT_HOLE_DEPTH': '10 mm',
})
doc.RecomputesFrozen = True


def sketchPcbOutline(sketch, offsetExpr: str | None = None):
  radiusExpr = f'Params.PCB_RADIUS + ({offsetExpr})' if offsetExpr else 'Params.PCB_RADIUS'
  bottomDistExpr = f'Params.PCB_BOTTOM_HALF_HEIGHT + ({offsetExpr})' if offsetExpr else 'Params.PCB_BOTTOM_HALF_HEIGHT'

  (be_r, be_arct, be_arcb, be_l, be_bl, be_b, be_br) = sketch.addGeometry([
    Part.LineSegment(App.Vector(20, -10), App.Vector(20, 0)),
    Part.Arc(App.Vector(20, 0), App.Vector(0, 20), App.Vector(-20, 0)),
    Part.Arc(App.Vector(-20, 0), App.Vector(0, -20), App.Vector(20, 0)),
    Part.LineSegment(App.Vector(-20, 0), App.Vector(-20, -10)),
    Part.LineSegment(App.Vector(-20, -10), App.Vector(-10, -20)),
    Part.LineSegment(App.Vector(-10, -20), App.Vector(10, -20)),
    Part.LineSegment(App.Vector(10, -20), App.Vector(20, -10)),
  ], False)

  sketch.addConstraint([
    Sketcher.Constraint('Coincident', be_arct, CA.CENTER, *ORIGIN),
    Sketcher.Constraint('PointOnObject', be_arct, CA.START_POINT, AxisId.X),
    Sketcher.Constraint('Coincident', be_arcb, CA.START_POINT, be_arct, CA.END_POINT),
    Sketcher.Constraint('PointOnObject', be_arcb, CA.END_POINT, AxisId.X),
  ])

  sketch.toggleConstruction(be_arcb)
  addExpressionConstraint(sketch, 'Radius', radiusExpr, be_arct)
  addExpressionConstraint(sketch, 'Radius', radiusExpr, be_arcb)
  addExpressionConstraint(sketch, 'Angle', '180', be_arct)
  addExpressionConstraint(sketch, 'Angle', '180', be_arcb)
  sketch.recompute()

  pcb_mockup_base_s_constraints = sketch.addConstraint(constrainCoincidentPath([be_r, be_br, be_b, be_bl, be_l]) + [
    Sketcher.Constraint('Vertical', be_l),
    Sketcher.Constraint('Vertical', be_r),
    Sketcher.Constraint('Symmetric', be_b, CA.START_POINT, be_b, CA.END_POINT, AxisId.Y),
    Sketcher.Constraint('PointOnObject', be_b, CA.START_POINT, be_arcb),
    Sketcher.Constraint('Coincident', be_l, CA.END_POINT, be_arct, CA.END_POINT),
    Sketcher.Constraint('Coincident', be_r, CA.START_POINT, be_arct, CA.START_POINT),
    Sketcher.Constraint('Angle', be_bl, CA.START_POINT, be_l, CA.END_POINT, math.radians(135)),
    Sketcher.Constraint('Angle', be_r, CA.START_POINT, be_br, CA.END_POINT, math.radians(135)),
  ])

  sketch.setDatum(pcb_mockup_base_s_constraints[-2], App.Units.Quantity('135 deg'))
  sketch.setDatum(pcb_mockup_base_s_constraints[-1], App.Units.Quantity('135 deg'))
  addExpressionConstraint(sketch, 'DistanceY', bottomDistExpr, be_b, CA.START_POINT, *ORIGIN)
  sketch.recompute()


def createPcbMockup(doc):
  pcb_mockup = doc.addObject("PartDesign::Body", "PCB_Mockup")
  xy_plane = pcb_mockup.Origin.OriginFeatures[3]

  pcb_mockup_base_s = pcb_mockup.newObject("Sketcher::SketchObject", f'{pcb_mockup.Label}_Base')
  pcb_mockup_base_s.AttachmentSupport = xy_plane
  sketchPcbOutline(pcb_mockup_base_s)

  pcb_mockup_base_pad = pcb_mockup.newObject('PartDesign::Pad', f'{pcb_mockup_base_s.Label}_Pad')
  pcb_mockup_base_pad.Profile = pcb_mockup_base_s
  pcb_mockup_base_pad.Type = 'Length'
  pcb_mockup_base_pad.setExpression('Length', 'Params.PCB_THICKNESS')

  return pcb_mockup


def createPcbEnvelope(doc):
  pcb_envelope = doc.addObject("PartDesign::Body", "PCB_Envelope")
  xy_plane = pcb_envelope.Origin.OriginFeatures[3]

  pcb_envelope_base_s = pcb_envelope.newObject("Sketcher::SketchObject", f'{pcb_envelope.Label}_Base')
  pcb_envelope_base_s.AttachmentSupport = xy_plane
  sketchPcbOutline(pcb_envelope_base_s, 'Params.PCB_OUTLINE_TOLERANCE + Params.PLA_EXPANSION')

  pcb_envelope_base_pad = pcb_envelope.newObject('PartDesign::Pad', f'{pcb_envelope_base_s.Label}_Pad')
  pcb_envelope_base_pad.Profile = pcb_envelope_base_s
  pcb_envelope_base_pad.Type = 'Length'
  pcb_envelope_base_pad.setExpression('Length', 'Params.PCB_THICKNESS + Params.PLA_EXPANSION')

  # SAO pins clearance
  pcb_envelope_saobox = pcb_envelope.newObject("PartDesign::AdditiveBox", f'{pcb_envelope.Label}_SAOBox')
  pcb_envelope_saobox.AttachmentSupport = xy_plane
  pcb_envelope_saobox.MapMode = 'ObjectXY'
  pcb_envelope_saobox.setExpression('AttachmentOffset.Base.z', 'Params.PCB_THICKNESS')
  pcb_envelope_saobox.setExpression('Length', '8 mm')
  pcb_envelope_saobox.setExpression('Width', '5.4 mm')
  pcb_envelope_saobox.setExpression('Height', '2 mm')
  pcb_envelope_saobox.setExpression('AttachmentOffset.Base.x', '-Length/2')
  pcb_envelope_saobox.setExpression('AttachmentOffset.Base.y', '-4.5 mm - (Width/2)')

  # LEDs space
  def createLedEnvelope(ledNum: int, baseYExpr: str, baseXExpr: str):
    led_cone = pcb_envelope.newObject("PartDesign::AdditiveCone", f'{pcb_envelope.Label}_LED{ledNum}_Cone')
    led_cone.AttachmentSupport = xy_plane
    led_cone.MapMode = 'ObjectXY'
    led_cone.setExpression('AttachmentOffset.Base.z', 'Params.PCB_THICKNESS')
    led_cone.setExpression('AttachmentOffset.Base.y', baseYExpr)
    led_cone.setExpression('AttachmentOffset.Base.x', baseXExpr)
    led_cone.setExpression('Radius2', '(3.2 mm + 0.2 mm)/2 + Params.PLA_EXPANSION')
    led_cone.setExpression('Height', '1 mm + 0.2 mm + Params.PLA_EXPANSION')
    led_cone.setExpression('Radius1', 'Radius2 + Height * sqrt(2)')

    led_shaft = pcb_envelope.newObject("PartDesign::AdditiveCylinder", f'{pcb_envelope.Label}_LED{ledNum}_Shaft')
    led_shaft.AttachmentSupport = xy_plane
    led_shaft.MapMode = 'ObjectXY'
    led_shaft.setExpression('AttachmentOffset.Base.z', 'Params.PCB_THICKNESS')
    led_shaft.setExpression('AttachmentOffset.Base.y', baseYExpr)
    led_shaft.setExpression('AttachmentOffset.Base.x', baseXExpr)
    led_shaft.setExpression('Radius', '(3 mm + 0.2 mm)/2 + Params.PLA_EXPANSION')
    led_shaft.setExpression('Height', '5.1 mm + 0.2 mm + Params.PLA_EXPANSION')

  createLedEnvelope(1, '(3 mm)/2', '-4.35 mm')
  createLedEnvelope(2, '(3 mm)/2', '4.35 mm')
  createLedEnvelope(3, '4.35 mm', '0')

  # Mounting hole space
  pcb_envelope_heatinserthole = pcb_envelope.newObject("PartDesign::AdditiveCylinder", f'{pcb_envelope.Label}_HeatInsertHole')
  pcb_envelope_heatinserthole.AttachmentSupport = xy_plane
  pcb_envelope_heatinserthole.MapMode = 'ObjectXY'
  pcb_envelope_heatinserthole.setExpression('AttachmentOffset.Base.z', 'Params.PCB_THICKNESS')
  pcb_envelope_heatinserthole.setExpression('AttachmentOffset.Base.y', '-Params.PCB_BOTTOM_HALF_HEIGHT + 2.4 mm')
  pcb_envelope_heatinserthole.setExpression('Radius', 'Params.HEAT_INSERT_HOLE_DIAM/2')
  pcb_envelope_heatinserthole.setExpression('Height', 'Params.HEAT_INSERT_HOLE_DEPTH')

  return pcb_envelope


pcb_envelope = createPcbEnvelope(doc)

if IMPORT_STEP:
  print('Importing PCB STEP file...')
  pcb_import_shape = Part.read('../hardware/exports/pcb.step')
  print("> Imported shape type:", pcb_import_shape.ShapeType)
  print("> Number of solids:", len(pcb_import_shape.Solids))
  pcb_import = doc.addObject("Part::Feature", "PCB_Import")
  pcb_import.Shape = pcb_import_shape
  pcb_import.setExpression('Placement.Base.x', '-100 mm')
  pcb_import.setExpression('Placement.Base.y', '100 mm')

# Save FreeCAD document
doc.RecomputesFrozen = False
doc.recompute()
doc.saveAs("exports/enclosure.FCStd")


# Export DXF
def exportDXF(source_obj, path: str):
  planar_faces = [f for f in source_obj.Shape.Faces if f.Surface.isPlanar()]
  if not planar_faces:
    raise ValueError('No planar faces available for DXF export')

  reference_face = max(planar_faces, key=lambda f: f.Area)
  reference_axis = reference_face.Surface.Axis
  reference_center = reference_face.BoundBox.Center

  def is_coplanar(face):
    axis = face.Surface.Axis
    if abs(abs(axis.dot(reference_axis)) - 1.0) > 1e-6:
      return False
    face_center = face.BoundBox.Center
    return abs(reference_axis.dot(face_center - reference_center)) < 1e-6

  coplanar_faces = [f for f in planar_faces if is_coplanar(f)]

  projection_source = doc.addObject('Part::Feature', 'PCB_DXF_Projection_Source')
  projection_source.Shape = Part.Compound(coplanar_faces)

  projection = Draft.make_shape2dview(projection_source, projectionVector=reference_axis)
  projection.Label = f'{source_obj.Label}_DXF'
  projection_bbox_center = projection.Shape.BoundBox.Center
  projection.Placement.Base = projection_bbox_center
  projection.recompute()
  source_obj.addObject(projection)

  importDXF.export([projection], path)
  doc.removeObject(projection_source.Name)

if EXPORT_DXF:
  pcb_mockup = createPcbMockup(doc)
  exportDXF(pcb_mockup, "exports/pcb-outline.dxf")


# Export STL
def export_to_stl(obj, export_path):
  # High-definition mesh parameters
  linear_deflection = 0.01
  angular_deflection = math.radians(0.5)
  relative = False

  print(f'Building mesh from {obj.Name}...')
  mesh = MeshPart.meshFromShape(obj.Shape, linear_deflection, angular_deflection, relative)

  # Mesh must be a document object for export
  mesh_obj = doc.addObject('Mesh::Feature', f'{obj.Name}_Mesh')
  mesh_obj.Mesh = mesh
  doc.recompute()

  print(f'Exporting mesh to {export_path}...')
  Mesh.export([mesh_obj], export_path)

if EXPORT_STL:
  export_to_stl(pcb_mockup, 'exports/enclosure.stl')
