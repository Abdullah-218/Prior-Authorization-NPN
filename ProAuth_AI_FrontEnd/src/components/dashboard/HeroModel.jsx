import { useEffect, useRef, useState } from 'react';
import { ContactShadows, Environment } from '@react-three/drei';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

const ecgCurve = new THREE.CatmullRomCurve3([
  new THREE.Vector3(-1.25, 0, 0),
  new THREE.Vector3(-0.95, 0, 0),
  new THREE.Vector3(-0.78, 0.08, 0),
  new THREE.Vector3(-0.58, 0, 0),
  new THREE.Vector3(-0.36, 0, 0),
  new THREE.Vector3(-0.22, 0.12, 0),
  new THREE.Vector3(-0.08, -0.42, 0),
  new THREE.Vector3(0.08, 0.72, 0),
  new THREE.Vector3(0.2, -0.18, 0),
  new THREE.Vector3(0.38, 0, 0),
  new THREE.Vector3(0.62, 0.08, 0),
  new THREE.Vector3(0.82, 0, 0),
  new THREE.Vector3(1.25, 0, 0)
]);

function ECGWaveform({ animated }) {
  const pulseRef = useRef();
  useFrame(state => {
    if (!animated) return;
    const progress = (state.clock.elapsedTime * 0.16) % 1;
    pulseRef.current.position.copy(ecgCurve.getPointAt(progress));
  });
  return <group position={[0, -0.05, 0.08]} scale={0.82}><mesh><tubeGeometry args={[ecgCurve, 64, 0.025, 6, false]}/><meshStandardMaterial color="#4b9b95" roughness={0.55} metalness={0.05}/></mesh><mesh ref={pulseRef} position={[-1.25, 0, 0]}><sphereGeometry args={[0.07, 12, 8]}/><meshStandardMaterial color="#4b9b95" emissive="#4b9b95" emissiveIntensity={0.35} roughness={0.45}/></mesh></group>;
}

function Instrument({ animated }) {
  const groupRef = useRef();
  useFrame((state, delta) => {
    if (!animated) return;
    groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.35) * 0.12;
    groupRef.current.position.y = Math.sin(state.clock.elapsedTime * 0.7) * 0.035;
    groupRef.current.rotation.z = THREE.MathUtils.damp(groupRef.current.rotation.z, -0.08, 3, delta);
  });
  return <group ref={groupRef}><ECGWaveform animated={animated}/></group>;
}

export default function HeroModel() {
  const containerRef = useRef();
  const [visible, setVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateMotion = () => setReducedMotion(motionQuery.matches);
    updateMotion();
    motionQuery.addEventListener?.('change', updateMotion);
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.01 });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => { motionQuery.removeEventListener?.('change', updateMotion); observer.disconnect(); };
  }, []);

  return <div ref={containerRef} className="hero-model" aria-label="Clinical intelligence platform"><Canvas frameloop={visible && !reducedMotion ? 'always' : 'demand'} dpr={[1, 1.5]} camera={{ position: [0, 0, 3.2], fov: 42 }} shadows><color attach="background" args={['#f7fafb']}/><ambientLight intensity={0.5}/><directionalLight position={[3, 4, 5]} intensity={1} castShadow/><directionalLight position={[-4, 2, -3]} intensity={0.35} color="#bcdcff"/><Environment preset="studio" intensity={0.3}/><Instrument animated={visible && !reducedMotion}/><ContactShadows position={[0, -1, 0]} opacity={0.18} scale={2} blur={2.4} far={3}/></Canvas></div>;
}
