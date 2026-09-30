/**
 * The screen for the browser's session against a real API: nothing while the session is read,
 * then the sign-in page, the "Choose a new password" page, the platform portal or the Studio.
 */
import { useEffect } from 'react';

import { App } from '../App';
import { PlatformPortal } from '../platform/PlatformPortal';
import { auth, useAuth } from './authStore';
import { ChoosePassword } from './ChoosePassword';
import { SignIn } from './SignIn';

export function Gate() {
  const { mode } = useAuth();
  useEffect(() => {
    void auth.boot();
  }, []);
  switch (mode) {
    case 'loading':
      return null;
    case 'signIn':
      return <SignIn />;
    case 'password':
      return <ChoosePassword />;
    case 'platform':
      return <PlatformPortal />;
    case 'studio':
      return <App />;
  }
}
