// Bundled for the optional 3D research viewer. Runtime code loads this file
// only after the viewer is opened; the main assessor has no Three.js cost.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

globalThis.HD2Three = { THREE, GLTFLoader, OrbitControls };

