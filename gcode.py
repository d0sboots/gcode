#!/usr/bin/python

from datetime import datetime
import math
import sys

class GCode(object):

  def __init__(self, filament_diameter, extrusion_width,
               default_layer_height=0.2, destination=sys.stdout):
    self.filament_diameter = filament_diameter
    self.extrusion_width = extrusion_width
    self.destination = destination
    self.default_layer_height = default_layer_height
    self.suck_mm = 15.0
    self.clearance = 0.3
    self.default_feedrate = 990


  def start(self):
    print >>self.destination, """
; {BINARY}
; Generated on {DATE}
;
; *** Settings ***
"""[1:-1].format(BINARY=sys.argv[0],
                 DATE=datetime.now().ctime())
    for setting in ["filament_diameter", "extrusion_width",
                    "default_layer_height", "suck_mm", "clearance",
                    "default_feedrate"]:
      print >>self.destination, "; %s = %s" % (setting, getattr(self, setting))
    print >>self.destination, """
;
; *** G-code Preamble ***

G21  ; [mm] mode
G90  ; absolute mode
T0  ; Select extruder 0
M104 S245  ; preheat to 245 but don't wait
G28  ; home to top endstops
G29  ; FSR autolevel and adjust first layer thickness

G92 E0  ; reset extruder pos

G1 X0 Y0 Z0.5 F18000  ; Fast move to a known location

; *** Main G-code ***

"""[1:-1]

    self.x = 0.0
    self.y = 0.0
    self.z = 0.5
    self.e = 0.0
    self.feedrate = 18000


  def finish(self):
    print >>self.destination, """

; *** Coda ***

M104 S0  ; cool extruder
G28  ; home to top endstops
"""[1:-1]


  def __enter__(self):
    self.start()
    return self


  def __exit__(self, *unused):
    self.finish()


  def g1(self, x=None, y=None, z=None, layer_height=None, feedrate=None):
    cmds = ["G1"]

    if x is None or x == self.x:
      dx = 0
    else:
      dx = x - self.x
      self.x = x
      cmds.append("X%.2f" % x)
    if y is None or y == self.y:
      dy = 0
    else:
      dy = y - self.y
      self.y = y
      cmds.append("Y%.2f" % y)
    if z is None or z == self.z:
      dz = 0
    else:
      dz = z - self.z
      self.z = z
      cmds.append("Z%.2f" % z)
    if layer_height is None:
      layer_height = self.default_layer_height

    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
    e_len = dist * self.extrusion_width * layer_height / (
        (self.filament_diameter / 2.0)**2 * math.pi)
    self.e += e_len
    if e_len >= .0001:
      cmds.append("E%.4f" % self.e)

    if feedrate is not None and feedrate != self.feedrate:
      cmds.append("F%d" % feedrate)
      self.feedrate = feedrate

    print >>self.destination, " ".join(cmds)


  def extrude(self, extrude_mm):
    self.e += extrude_mm
    print >>self.destination, "G1 E%.4f F6000" % self.e
    self.feedrate = 6000


  def output(self, string):
    print >>self.destination, string


  def skirt(self, radius=50.0):
    self.output("\n; Custom skirt with radius %f" % radius)
    self.g1(radius, 0, self.default_layer_height + self.clearance,
            layer_height=0, feedrate=18000)
    self.g1(z=self.default_layer_height, layer_height=0, feedrate=1200)
    self.output("; Wait 15s to give heating time")
    self.output("G4 P15000")
    self.extrude(2.0)
    self.output("; Wait another 5s to melt the primed filament")
    self.output("G4 P5000")
    self.extrude(5.0)
    num_arcs = 500
    end = num_arcs + 10
    for arc in range(end + 1):
      angle = (math.pi * 2 / num_arcs) * (arc + 1)
      x = (radius + angle * 1.5) * math.cos(angle)
      y = (radius + angle * 1.5) * math.sin(angle)
      if arc < end:
        self.g1(x, y, layer_height=self.default_layer_height * 1.2,
                feedrate=self.default_feedrate)
      else:
        self.wipe(x * (1 - 12.0 / radius), y * (1 - 12.0 / radius))


  def wipe(self, x, y):
    self.output("; Wipe")
    self.extrude(-self.suck_mm)
    self.g1(x, y, layer_height=0, feedrate=2400)


  def clean_move(self, x, y):
    saved_z = self.z
    self.g1(z=(self.z + self.clearance), layer_height=0, feedrate=12000)
    self.g1(x, y, layer_height=0, feedrate=18000)
    self.g1(z=saved_z, layer_height=0, feedrate=12000)


  def spiral(self, radius, height):
    self.output("\n; Spiral, radius=%f, height=%f" % (radius, height))
    num_arcs = 300
    full_begin = num_arcs
    full_end = int(num_arcs * height / self.default_layer_height)
    true_end = full_end + num_arcs
    step_height = self.default_layer_height / num_arcs
    for arc in range(true_end + 2):
      angle = (math.pi * 2 / num_arcs) * arc
      x = radius * math.cos(angle)
      y = radius * math.sin(angle)
      z = float(arc) * step_height
      if arc < full_begin:
        # Adjust layer_height by half a step, because we're making a
        # trapezoid, so the the volume == the volume of a rectangle with the
        # average height of the two endpoints.
        #layer_height = z + step_height / 2.0
        #fr = self.default_feedrate / layer_height * self.default_layer_height
        #fr = min(fr, 3600)
        self.g1(x, y, self.default_layer_height, feedrate=self.default_feedrate)
      elif arc <= full_end:
        if arc == full_begin:
          self.output("\n; First layer")
          self.output("M104 S235")
        self.g1(x, y, z, feedrate=self.default_feedrate)
      elif arc <= true_end:
        # Finish at the same height, with ever decreasing layer_height. The
        # same trapezoid adjustment applies here.
        #layer_height = self.default_layer_height + height - z + step_height / 2.0
        #fr = self.default_feedrate / layer_height * self.default_layer_height
        #fr = min(fr, 3600)
        self.g1(x, y, height, feedrate=self.default_feedrate)
      else:
        self.wipe(x + 2.0, y)


  def hemispiral(self, radius, start=0.0, end=math.pi/2, top_width=None):
    if top_width is None:
      top_width = self.extrusion_width - .01
    self.output("\n; Hemi-Spiral, radius=%f, start=%f, end=%f, top_width=%f" %
        (radius, start, end, top_width))
    tolerance = .005
    # We want the width of each line to vary with phi^2. The width of a
    # line is determined by the change in phi per theta. In other words:
    #
    # d(phi)/d(theta) = k0 + k1*phi^2
    #
    # Solving this yields:
    #
    # phi = sqrt(k0/k1) * tan(sqrt(k0*k1)*(c+x))
    #
    # If we want phi to be phi0 when theta = 0, that determines the value of c:
    #
    # c = tan^-1(phi0 / sqrt(k0/k1)) / sqrt(k0 * k1)
    #
    # phi = sqrt(k0/k1) * tan(sqrt(k0*k1)*x + tan^-1(phi0 / sqrt(k0/k1)))
    k0 = self.default_layer_height / (radius * math.pi * 2.0)
    k1 = (top_width / (radius * math.pi * 2.0) - k0) / (math.pi / 2.0)**2
    if k1 == 0.0:
      phi = lambda theta: start + k0 * theta
    else:
      k2 = math.sqrt(k0 / k1)
      k3 = math.sqrt(k0 * k1)
      k4 = math.atan(start / k2)
      phi = lambda theta: k2 * math.tan(k3 * theta + k4)
    c_phi = phi(0)
    z_adjust = radius * -math.sin(c_phi) + self.default_layer_height

    theta = -2 * math.pi
    d_theta = .001

    x = radius * math.cos(c_phi)
    y = 0.0
    z = self.default_layer_height
    self.g1(x, y, z, feedrate=self.default_feedrate)

    while c_phi < end:
      n_theta = theta + d_theta
      n_phi = phi(n_theta)
      n_radius = radius * math.cos(n_phi)
      n_x = n_radius * math.cos(n_theta)
      n_y = n_radius * math.sin(n_theta)
      n_z = radius * math.sin(n_phi) + z_adjust

      h_theta = theta + d_theta / 2.0
      h_phi = phi(h_theta)
      h_radius = radius * math.cos(h_phi)
      h_x = h_radius * math.cos(h_theta)
      h_y = h_radius * math.sin(h_theta)
      h_z = radius * math.sin(h_phi) + z_adjust

      #print x, y, z, h_x, h_y, h_z, n_x, n_y, n_y, c_phi, h_phi, n_phi, theta, h_theta, n_theta
      err = math.sqrt((h_x - (n_x + x) / 2.0)**2 +
                      (h_y - (n_y + y) / 2.0)**2 +
                      (h_z - (n_z + z) / 2.0)**2)

      #self.output("; err = %f, d_theta = %f" % (err, d_theta))

      d_theta *= math.sqrt(tolerance / err)
      x = n_x
      y = n_y
      z = n_z
      c_phi = n_phi

      if n_theta < 0:
        n_radius = radius * math.cos(phi(0))
        n_x = n_radius * math.cos(n_theta)
        n_y = n_radius * math.sin(n_theta)
        n_z = self.default_layer_height
      elif theta < 0:
        self.output("\n; First layer")
        self.output("; backfeed slightly to reduce pressure")
        self.extrude(-1)
        self.output("M104 S235")

      self.g1(n_x, n_y, n_z, feedrate=self.default_feedrate)
      theta = n_theta

    self.wipe(0, 0)
    self.g1(z=100, layer_height=0, feedrate=18000)


  def scaffold(self, radius, gap):
    self.output("\n; Support, radius=%f, gap=%f" % (radius, gap))
    num_arcs = 2
    arc_limits = [self.extrusion_width / 2.0]
    while radius * 2.0 * math.pi / num_arcs > gap:
      arc_limits.append(gap * num_arcs / (2.0 * math.pi))
      num_arcs = num_arcs << 1
    self.output("; num_arcs=%d, arc_limits=%s" % (num_arcs, arc_limits))
    for layer in range(1, 20):
      self.g1(z=layer * self.default_layer_height, layer_height=0)
      if layer == 2:
        self.output("M104 S235")
      for arc in range(num_arcs):
        angle = math.pi * 2.0 * arc / num_arcs
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        self.g1(x, y, layer_height=0, feedrate=12000)
        bit = 1
        idx = len(arc_limits) - 1
        while idx and arc & bit == 0:
          bit = bit << 1
          idx -= 1
        x *= arc_limits[idx] / radius
        y *= arc_limits[idx] / radius
        self.g1(x, y, feedrate=self.default_feedrate)
    self.extrude(-self.suck_mm)
    x *= .5
    y *= .5
    self.g1(x, y, layer_height=0, feedrate=12000)


  def test_destring(self):
    self.g1(10, 10, 0.4, layer_height=0, feedrate=12000)
    self.g1(10, 10, 0, layer_height=0, feedrate=12000)
    z = 0.0
    for layers in range(10):
      z += self.default_layer_height / 4.0
      self.g1(10, -10, z, feedrate=self.default_feedrate)
      z += self.default_layer_height / 4.0
      self.g1(-10, -10, z, feedrate=self.default_feedrate)
      z += self.default_layer_height / 4.0
      self.g1(-10, 10, z, feedrate=self.default_feedrate)
      z += self.default_layer_height / 4.0
      self.g1(10, 10, z, feedrate=self.default_feedrate)

    for layers in range(100):
      suck = layers / 10.0

      z += self.default_layer_height / 4.0
      self.g1(10, -10, z, feedrate=self.default_feedrate)
      z += self.default_layer_height / 4.0
      self.g1(-10, -10, z, feedrate=self.default_feedrate)
      z += self.default_layer_height / 4.0
      self.g1(-10, 10, z, feedrate=self.default_feedrate)
      self.extrude(-suck)
      self.g1(-10, -10, z, layer_height=0, feedrate=12000)
      self.g1(10, -10, z, layer_height=0)
      self.g1(10, 10, z, layer_height=0)
      z += self.default_layer_height / 4.0
      self.g1(10, 10, z, layer_height=0)
      self.extrude(suck)


if __name__ == "__main__":
  with GCode(filament_diameter=1.72, extrusion_width=0.3,
             default_layer_height=.29) as g:
    g.skirt()
    g.clean_move(75 * math.cos(.44 * math.pi), 0)
    g.extrude(g.suck_mm)
    g.hemispiral(75, start=(math.pi * -.44), end=(math.pi * .44), top_width=.29)
    #g.hemispiral(25, start=(math.pi * .25), end=(math.pi * .45), top_width=.29)
    #g.hemispiral(25, start=(math.pi * -.40), end=(math.pi * .40), top_width=.29)
