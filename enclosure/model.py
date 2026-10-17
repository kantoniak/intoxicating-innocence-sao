from helpers import *
from helpers import ConstraintAttachment as CA
import importDXF
import math
import Draft
import FreeCAD as App
import MeshPart, Mesh

EXPORT_DXF = True
EXPORT_STL = False

doc = App.newDocument("Enclosure")
Params = initParams(doc, {
  'PCB_RADIUS': '18 mm',
  'PCB_BOTTOM_HALF_HEIGHT': '14 mm',
  'PCB_THICKNESS': '1.6 mm',
})
doc.RecomputesFrozen = True

def createPcbMockup(doc):
  pcb_mockup = doc.addObject("PartDesign::Body", "PCB_Mockup")
  xy_plane = pcb_mockup.Origin.OriginFeatures[3]

  pcb_mockup_base_s = pcb_mockup.newObject("Sketcher::SketchObject", f'{pcb_mockup.Label}_Base')
  pcb_mockup_base_s.AttachmentSupport = xy_plane

  (be_r, be_arct, be_arcb, be_l, be_bl, be_b, be_br) = pcb_mockup_base_s.addGeometry([
        Part.LineSegment(App.Vector(20, -10), App.Vector(20, 0)),
        Part.Arc(App.Vector(20, 0), App.Vector(0, 20), App.Vector(-20, 0)),
        Part.Arc(App.Vector(-20, 0), App.Vector(0, -20), App.Vector(20, 0)),
        Part.LineSegment(App.Vector(-20, 0), App.Vector(-20, -10)),
        Part.LineSegment(App.Vector(-20, -10), App.Vector(-10, -20)),
        Part.LineSegment(App.Vector(-10, -20), App.Vector(10, -20)),
        Part.LineSegment(App.Vector(10, -20), App.Vector(20, -10)),
      ], False)

  pcb_mockup_base_s.addConstraint([
    Sketcher.Constraint('Coincident', be_arct, CA.CENTER, *ORIGIN),
    Sketcher.Constraint('PointOnObject', be_arct, CA.START_POINT, AxisId.X),
    #Sketcher.Constraint('PointOnObject', be_arct, CA.END_POINT, AxisId.X),
    #Sketcher.Constraint('Coincident', be_arcb, CA.CENTER, be_arct, CA.CENTER),
    Sketcher.Constraint('Coincident', be_arcb, CA.START_POINT, be_arct, CA.END_POINT),
    Sketcher.Constraint('PointOnObject', be_arcb, CA.END_POINT, AxisId.X),
  ])

  pcb_mockup_base_s.toggleConstruction(be_arcb)
  addExpressionConstraint(pcb_mockup_base_s, 'Radius', 'Params.PCB_RADIUS', be_arct)
  addExpressionConstraint(pcb_mockup_base_s, 'Radius', 'Params.PCB_RADIUS', be_arcb)
  addExpressionConstraint(pcb_mockup_base_s, 'Angle', '180', be_arct)
  addExpressionConstraint(pcb_mockup_base_s, 'Angle', '180', be_arcb)
  pcb_mockup_base_s.recompute()

  pcb_mockup_base_s_constraints = pcb_mockup_base_s.addConstraint(constrainCoincidentPath([be_r, be_br, be_b, be_bl, be_l]) + [
    Sketcher.Constraint('Vertical', be_l),
    Sketcher.Constraint('Vertical', be_r),
    Sketcher.Constraint('Symmetric', be_b, CA.START_POINT, be_b, CA.END_POINT, AxisId.Y),
    Sketcher.Constraint('PointOnObject', be_b, CA.START_POINT, be_arcb),
    Sketcher.Constraint('Coincident', be_l, CA.END_POINT, be_arct, CA.END_POINT),
    Sketcher.Constraint('Coincident', be_r, CA.START_POINT, be_arct, CA.START_POINT),
    Sketcher.Constraint('Angle', be_bl, CA.START_POINT, be_l, CA.END_POINT, math.radians(135)),
    Sketcher.Constraint('Angle', be_r, CA.START_POINT, be_br, CA.END_POINT, math.radians(135)),
  ])

  pcb_mockup_base_s.setDatum(pcb_mockup_base_s_constraints[-2], App.Units.Quantity('135 deg'))
  pcb_mockup_base_s.setDatum(pcb_mockup_base_s_constraints[-1], App.Units.Quantity('135 deg'))
  addExpressionConstraint(pcb_mockup_base_s, 'DistanceY', 'Params.PCB_BOTTOM_HALF_HEIGHT', be_b, CA.START_POINT, *ORIGIN)
  pcb_mockup_base_s.recompute()

  pcb_mockup_base_pad = pcb_mockup.newObject('PartDesign::Pad', f'{pcb_mockup_base_s.Label}_Pad')
  pcb_mockup_base_pad.Profile = pcb_mockup_base_s
  pcb_mockup_base_pad.Type = 'Length'
  pcb_mockup_base_pad.setExpression('Length', 'Params.PCB_THICKNESS')

  return pcb_mockup

pcb_mockup = createPcbMockup(doc)

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
